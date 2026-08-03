/*
 * HERA — cola durable de reflexión (E4, paso 1). Ver hera_queue.h.
 *
 * Mismo patrón que el almacén, y por las mismas razones: diario de solo
 * añadir, estado derivado leyéndolo entero, y relectura + decisión + escritura
 * dentro del MISMO cerrojo exclusivo. Partirlo en dos tramos es tener una
 * carrera en la que dos trabajadores se llevan el mismo job.
 *
 * El cerrojo es un fichero propio (`hera_cola.lock`) y no el del almacén: un
 * trabajador que esté tomando un job no tiene por qué bloquear a un turno que
 * solo quiere leer el perfil.
 */

#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif

#include "hera_queue.h"

#include <errno.h>
#include <fcntl.h>
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <signal.h>
#include <sys/file.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>

#define JOBS_MAX   1024
#define LINEA_MAX  (HERA_JOB_TEXTO_MAX * 4)

static hera_job_t      g_jobs[JOBS_MAX];
static size_t          g_jobs_n;
static char            g_ruta[1200];
static bool            g_abierta;
static int             g_lock_fd = -1;
static int             g_lock_prof;
static pthread_mutex_t g_mtx = PTHREAD_RECURSIVE_MUTEX_INITIALIZER_NP;

static void recargar(void);

/* ------------------------------------------------------------------------
 * DUEÑO DE UN JOB. Al abrir hay que distinguir dos cosas que sobre el papel
 * se parecen: un job TOMADO por un trabajador que murió (hay que devolverlo a
 * la cola) y uno TOMADO por un trabajador que sigue trabajando (tocarlo es
 * robárselo, y entonces dos trabajadores reflexionan el mismo turno y el
 * recuerdo se duplica — justo lo que la cola existe para impedir).
 *
 * El dueño es `<boot_id>:<pid>`:
 *   · pid distinto y proceso vivo  -> lo tiene alguien, no se toca.
 *   · proceso muerto               -> abandonado, vuelve a la cola.
 *   · boot_id distinto             -> la máquina se reinició, todos muertos.
 *     Sin esto, tras un reinicio un pid reutilizado por cualquier otro
 *     programa haría que un job abandonado pareciera vivo para siempre.
 * ------------------------------------------------------------------------ */
static void dueno_actual(char *out, size_t cap) {
    char boot[64] = "sinboot";
    FILE *f = fopen("/proc/sys/kernel/random/boot_id", "r");
    if (f) {
        if (fgets(boot, sizeof(boot), f)) {
            boot[strcspn(boot, "\n")] = '\0';
            boot[8] = '\0';           /* prefijo: basta para distinguir */
        }
        fclose(f);
    }
    snprintf(out, cap, "%s:%d", boot, (int)getpid());
}

static bool dueno_vivo(const char *dueno) {
    if (!dueno || !*dueno) return false;
    char yo[80];
    dueno_actual(yo, sizeof(yo));
    const char *dp = strchr(dueno, ':'), *yp = strchr(yo, ':');
    if (!dp || !yp) return false;
    /* Otra arrancada de la máquina: nadie de entonces sigue vivo. */
    if ((size_t)(dp - dueno) != (size_t)(yp - yo) ||
        strncmp(dueno, yo, (size_t)(dp - dueno)) != 0) return false;
    const int pid = atoi(dp + 1);
    if (pid <= 0) return false;
    return kill((pid_t)pid, 0) == 0 || errno == EPERM;
}

const char *hera_job_estado_nombre(hera_job_estado_t e) {
    switch (e) {
        case HERA_JOB_PENDIENTE: return "pendiente";
        case HERA_JOB_TOMADO:    return "tomado";
        case HERA_JOB_HECHO:     return "hecho";
        case HERA_JOB_FALLIDO:   return "fallido";
    }
    return "?";
}

static void bloquear(int op) {
    pthread_mutex_lock(&g_mtx);
    if (g_lock_prof++ == 0 && g_lock_fd >= 0) {
        while (flock(g_lock_fd, op) != 0 && errno == EINTR) { }
    }
}

static void desbloquear(void) {
    if (--g_lock_prof == 0 && g_lock_fd >= 0) flock(g_lock_fd, LOCK_UN);
    pthread_mutex_unlock(&g_mtx);
}

/* ------------------------------------------------------------------------ */

static void esc(const char *s, char *out, size_t cap) {
    size_t o = 0;
    for (const unsigned char *p = (const unsigned char *)s; *p && o + 8 < cap; p++) {
        switch (*p) {
            case '"':  out[o++] = '\\'; out[o++] = '"';  break;
            case '\\': out[o++] = '\\'; out[o++] = '\\'; break;
            case '\n': out[o++] = '\\'; out[o++] = 'n';  break;
            case '\t': out[o++] = '\\'; out[o++] = 't';  break;
            case '\r': break;
            default:
                if (*p < 0x20) o += (size_t)snprintf(out + o, cap - o, "\\u%04x", *p);
                else out[o++] = (char)*p;
        }
    }
    out[o] = '\0';
}

static bool campo(const char *linea, const char *clave, char *out, size_t cap) {
    char pat[64];
    snprintf(pat, sizeof(pat), "\"%s\":", clave);
    const char *k = strstr(linea, pat);
    if (!k) return false;
    const char *q = strchr(k + strlen(pat), '"');
    if (!q) return false;
    size_t o = 0;
    for (const char *p = q + 1; *p && o + 1 < cap; p++) {
        if (*p == '\\') {
            p++;
            if (!*p) break;
            switch (*p) {
                case 'n':  out[o++] = '\n'; break;
                case 't':  out[o++] = '\t'; break;
                case '"':  out[o++] = '"';  break;
                case '\\': out[o++] = '\\'; break;
                default:   out[o++] = *p;
            }
            continue;
        }
        if (*p == '"') break;
        out[o++] = *p;
    }
    out[o] = '\0';
    return true;
}

static long long numero(const char *linea, const char *clave) {
    char pat[64];
    snprintf(pat, sizeof(pat), "\"%s\":", clave);
    const char *k = strstr(linea, pat);
    return k ? atoll(k + strlen(pat)) : 0;
}

static void directorio(char *out, size_t cap) {
    const char *custom = getenv("HELIOS_HOME");
    if (custom && *custom) snprintf(out, cap, "%s", custom);
    else {
        const char *home = getenv("HOME");
        snprintf(out, cap, "%s/.helios", home ? home : ".");
    }
    mkdir(out, 0755);
}

static long long ahora(void) {
    const char *fijo = getenv("HERA_TS_FIJO");
    if (fijo && *fijo) return atoll(fijo);
    return (long long)time(NULL);
}

static bool anexar(const char *linea) {
    FILE *f = fopen(g_ruta, "a");
    if (!f) return false;
    const size_t l = strlen(linea);
    const bool ok = fwrite(linea, 1, l, f) == l && fputc('\n', f) != EOF;
    return (fclose(f) == 0) && ok;
}

static hera_job_t *buscar(const char *id) {
    for (size_t i = 0; i < g_jobs_n; i++)
        if (strcmp(g_jobs[i].id, id) == 0) return &g_jobs[i];
    return NULL;
}

/* ------------------------------------------------------------------------ */

static void aplicar(const char *linea) {
    char r[24];
    if (!campo(linea, "r", r, sizeof(r))) return;
    char id[HERA_JOB_ID_MAX];
    if (!campo(linea, "job", id, sizeof(id))) return;

    if (strcmp(r, "encolado") == 0) {
#if HERA_SABOTAJE == 34
        /* Sabotaje: al releer, un "encolado" repetido crea otro job. Es la
         * segunda mitad de la idempotencia: sin ella, un diario con lineas
         * repetidas resucita trabajo duplicado en cada arranque. */
        if (g_jobs_n >= JOBS_MAX) return;
#else
        if (buscar(id) || g_jobs_n >= JOBS_MAX) return;
#endif
        hera_job_t *j = &g_jobs[g_jobs_n++];
        memset(j, 0, sizeof(*j));
        snprintf(j->id, sizeof(j->id), "%s", id);
        campo(linea, "perfil",     j->perfil,      sizeof(j->perfil));
        campo(linea, "sesion",     j->sesion,      sizeof(j->sesion));
        campo(linea, "mensaje",    j->mensaje,     sizeof(j->mensaje));
        campo(linea, "respuesta",  j->respuesta,   sizeof(j->respuesta));
        campo(linea, "acto",       j->acto,        sizeof(j->acto));
        campo(linea, "registro",   j->registro,    sizeof(j->registro));
        campo(linea, "evidencia",  j->evidencia,   sizeof(j->evidencia));
        campo(linea, "perfil_hash", j->perfil_hash, sizeof(j->perfil_hash));
        j->turno           = (unsigned)numero(linea, "turno");
        j->visible_budget  = (int)numero(linea, "visible_budget");
        j->thinking_budget = (int)numero(linea, "thinking_budget");
        j->estado = HERA_JOB_PENDIENTE;
        return;
    }
    hera_job_t *j = buscar(id);
    if (!j) return;
    if (strcmp(r, "tomado") == 0) {
        j->estado = HERA_JOB_TOMADO;
        j->dueno[0] = '\0';
        campo(linea, "dueno", j->dueno, sizeof(j->dueno));
    }
    else if (strcmp(r, "hecho") == 0)   j->estado = HERA_JOB_HECHO;
    else if (strcmp(r, "fallido") == 0) {
        j->estado = HERA_JOB_FALLIDO;
        campo(linea, "motivo", j->motivo, sizeof(j->motivo));
    } else if (strcmp(r, "aplazado") == 0) {
        /* Vuelve a la cola SIN tocar los intentos. */
        j->estado = HERA_JOB_PENDIENTE;
    } else if (strcmp(r, "reintento") == 0) {
        j->estado = HERA_JOB_PENDIENTE;
        j->intentos = (int)numero(linea, "intentos");
    }
}

static void recargar(void) {
    g_jobs_n = 0;
    FILE *f = fopen(g_ruta, "r");
    if (!f) return;
    char *linea = malloc(LINEA_MAX);
    if (linea) {
        while (fgets(linea, LINEA_MAX, f)) {
            size_t l = strlen(linea);
            if (l == 0 || linea[l - 1] != '\n') break;  /* cola a medias */
            linea[--l] = '\0';
            if (l && linea[l - 1] == '}') aplicar(linea);
        }
        free(linea);
    }
    fclose(f);
}

/* Recuperación: lo que quedó TOMADO es de un trabajador que ya no existe.
 * Vuelve a la cola con un intento más; agotados, FALLIDO y no vuelve — un job
 * que mata a su trabajador no puede quedarse delante de los demás para
 * siempre. Se escribe en el diario para que la cuenta de intentos sobreviva a
 * otro reinicio: si solo viviera en RAM, el bucle sería infinito con la
 * apariencia de estar recuperándose bien. */
static void recuperar_bajo_cerrojo(void) {
    for (size_t i = 0; i < g_jobs_n; i++) {
        hera_job_t *j = &g_jobs[i];
        if (j->estado != HERA_JOB_TOMADO) continue;
        /* Si su dueño sigue vivo, está trabajando: no es nuestro. */
        if (dueno_vivo(j->dueno)) continue;
        char linea[HERA_JOB_ID_MAX + 256];
        if (j->intentos + 1 >= HERA_JOB_INTENTOS) {
            snprintf(linea, sizeof(linea),
                     "{\"r\":\"fallido\",\"job\":\"%.*s\",\"ts\":%lld,"
                     "\"motivo\":\"agoto los intentos tras caidas\"}",
                     (int)sizeof(j->id) - 1, j->id, ahora());
            anexar(linea);
            j->estado = HERA_JOB_FALLIDO;
            snprintf(j->motivo, sizeof(j->motivo),
                     "agoto los intentos tras caidas");
        } else {
#if HERA_SABOTAJE == 33
            /* Sabotaje: se devuelve a la cola SIN anotar el intento, asi que
             * tras cada reinicio vuelve como nuevo: bucle infinito con toda
             * la apariencia de estar recuperandose bien. */
            j->estado = HERA_JOB_PENDIENTE;
#else
            snprintf(linea, sizeof(linea),
                     "{\"r\":\"reintento\",\"job\":\"%.*s\",\"ts\":%lld,"
                     "\"intentos\":%d}", (int)sizeof(j->id) - 1, j->id,
                     ahora(), j->intentos + 1);
            anexar(linea);
            j->estado = HERA_JOB_PENDIENTE;
            j->intentos++;
#endif
        }
    }
}

bool hera_cola_abrir(void) {
    char dir[1024];
    directorio(dir, sizeof(dir));
    snprintf(g_ruta, sizeof(g_ruta), "%s/hera_cola.jsonl", dir);

    if (g_lock_fd < 0) {
        char ruta_lock[1200];
        snprintf(ruta_lock, sizeof(ruta_lock), "%s/hera_cola.lock", dir);
        g_lock_fd = open(ruta_lock, O_RDWR | O_CREAT | O_CLOEXEC, 0644);
        if (g_lock_fd < 0) return false;
    }

    bloquear(LOCK_EX);
    FILE *f = fopen(g_ruta, "a");
    if (!f) { desbloquear(); return false; }
    fclose(f);
    recargar();
    recuperar_bajo_cerrojo();
    desbloquear();

    g_abierta = true;
    return true;
}

void hera_cola_cerrar(void) {
    g_abierta = false;
    g_jobs_n = 0;
    if (g_lock_fd >= 0) { close(g_lock_fd); g_lock_fd = -1; g_lock_prof = 0; }
}

const char *hera_cola_ruta(void) { return g_ruta; }

/* ------------------------------------------------------------------------ */

bool hera_cola_encolar(const hera_job_t *job) {
    if (!g_abierta || !job || !job->id[0]) return false;
    if (strlen(job->mensaje) >= HERA_JOB_TEXTO_MAX - 1 ||
        strlen(job->respuesta) >= HERA_JOB_TEXTO_MAX - 1) return false;

    bloquear(LOCK_EX);
    recargar();

#if HERA_SABOTAJE != 30
    /* Idempotente por identidad, no por buena memoria de quien llama. */
    if (buscar(job->id)) { desbloquear(); return true; }
#endif
    /* Sabotaje 30: encolar deja de ser idempotente y el mismo turno entra
     * tantas veces como se pida — un reinicio duplicaria los recuerdos. */
    if (g_jobs_n >= JOBS_MAX) { desbloquear(); return false; }

    char *m = malloc(HERA_JOB_TEXTO_MAX * 2);
    char *rp = malloc(HERA_JOB_TEXTO_MAX * 2);
    char *linea = malloc(LINEA_MAX);
    if (!m || !rp || !linea) {
        free(m); free(rp); free(linea); desbloquear(); return false;
    }
    esc(job->mensaje, m, HERA_JOB_TEXTO_MAX * 2);
    esc(job->respuesta, rp, HERA_JOB_TEXTO_MAX * 2);

    /* No hay campo para el contrato ni para el razonamiento interno. No es
     * disciplina: es que no existen. */
    snprintf(linea, LINEA_MAX,
        "{\"r\":\"encolado\",\"job\":\"%s\",\"ts\":%lld,\"perfil\":\"%s\","
        "\"sesion\":\"%s\",\"turno\":%u,\"acto\":\"%s\",\"registro\":\"%s\","
        "\"visible_budget\":%d,\"thinking_budget\":%d,\"evidencia\":\"%s\","
        "\"perfil_hash\":\"%s\",\"mensaje\":\"%s\",\"respuesta\":\"%s\"}",
        job->id, ahora(), job->perfil, job->sesion, job->turno,
        job->acto, job->registro, job->visible_budget, job->thinking_budget,
        job->evidencia, job->perfil_hash, m, rp);

    const bool ok = anexar(linea);
    if (ok) aplicar(linea);
    free(m); free(rp); free(linea);
    desbloquear();
    return ok;
}

bool hera_cola_tomar(hera_job_t *out) {
    if (!g_abierta || !out) return false;
    bloquear(LOCK_EX);
    recargar();

    hera_job_t *elegido = NULL;
    for (size_t i = 0; i < g_jobs_n; i++)
        if (g_jobs[i].estado == HERA_JOB_PENDIENTE) { elegido = &g_jobs[i]; break; }
    if (!elegido) { desbloquear(); return false; }

    char linea[512];
    char dueno[80];
    dueno_actual(dueno, sizeof(dueno));
    snprintf(linea, sizeof(linea),
             "{\"r\":\"tomado\",\"job\":\"%s\",\"ts\":%lld,\"dueno\":\"%s\"}",
             elegido->id, ahora(), dueno);
#if HERA_SABOTAJE == 31
    /* Sabotaje: tomar no deja marca, así que el siguiente que pregunte se
     * lleva el mismo job y el recuerdo se duplica. */
    (void)linea;
#else
    if (!anexar(linea)) { desbloquear(); return false; }
    elegido->estado = HERA_JOB_TOMADO;
#endif
    *out = *elegido;
    desbloquear();
    return true;
}

bool hera_cola_hecho(const char *id, size_t ops, size_t aceptables) {
    if (!g_abierta || !id) return false;
    bloquear(LOCK_EX);
    recargar();
    hera_job_t *j = buscar(id);
    if (!j) { desbloquear(); return false; }
    char linea[256];
    /* Números, nunca el texto. */
    snprintf(linea, sizeof(linea),
             "{\"r\":\"hecho\",\"job\":\"%s\",\"ts\":%lld,\"ops\":%zu,"
             "\"aceptables\":%zu}", id, ahora(), ops, aceptables);
    const bool ok = anexar(linea);
    if (ok) j->estado = HERA_JOB_HECHO;
    desbloquear();
    return ok;
}

bool hera_cola_fallido(const char *id, const char *motivo) {
    if (!g_abierta || !id) return false;
    bloquear(LOCK_EX);
    recargar();
    hera_job_t *j = buscar(id);
    if (!j) { desbloquear(); return false; }

    /* El motivo cabe entero o no cabe: recortarlo dejaria un diagnostico a
     * medias, que es peor que uno corto. */
    char mot[sizeof(((hera_job_t *)0)->motivo) * 2];
    esc(motivo ? motivo : "sin motivo", mot, sizeof(mot));
    char linea[sizeof(mot) + 256];
    bool ok;
    /* Fallar no bloquea la cola: si quedan intentos vuelve al final, y si no,
     * se cierra como fallido y los demás siguen pasando. */
    if (j->intentos + 1 < HERA_JOB_INTENTOS) {
        snprintf(linea, sizeof(linea),
                 "{\"r\":\"reintento\",\"job\":\"%s\",\"ts\":%lld,"
                 "\"intentos\":%d}", id, ahora(), j->intentos + 1);
        ok = anexar(linea);
        if (ok) { j->estado = HERA_JOB_PENDIENTE; j->intentos++; }
    } else {
        snprintf(linea, sizeof(linea),
                 "{\"r\":\"fallido\",\"job\":\"%s\",\"ts\":%lld,\"motivo\":\"%s\"}",
                 id, ahora(), mot);
        ok = anexar(linea);
        if (ok) {
            j->estado = HERA_JOB_FALLIDO;
            snprintf(j->motivo, sizeof(j->motivo), "%s", motivo ? motivo : "");
        }
    }
    desbloquear();
    return ok;
}

bool hera_cola_aplazado(const char *id) {
    if (!g_abierta || !id) return false;
    bloquear(LOCK_EX);
    recargar();
    hera_job_t *j = buscar(id);
    if (!j) { desbloquear(); return false; }
    char linea[HERA_JOB_ID_MAX + 128];
    snprintf(linea, sizeof(linea),
             "{\"r\":\"aplazado\",\"job\":\"%.*s\",\"ts\":%lld}",
             (int)sizeof(j->id) - 1, id, ahora());
    const bool ok = anexar(linea);
    if (ok) j->estado = HERA_JOB_PENDIENTE;   /* intentos intactos */
    desbloquear();
    return ok;
}

size_t hera_cola_pendientes(void) {
    size_t n = 0;
    bloquear(LOCK_SH);
    recargar();
    for (size_t i = 0; i < g_jobs_n; i++)
        if (g_jobs[i].estado == HERA_JOB_PENDIENTE) n++;
    desbloquear();
    return n;
}

size_t hera_cola_estado_json(char *out, size_t cap) {
    if (!out || !cap) return 0;
    size_t p = 0, t = 0, h = 0, f = 0;
    bloquear(LOCK_SH);
    recargar();
    for (size_t i = 0; i < g_jobs_n; i++) {
        switch (g_jobs[i].estado) {
            case HERA_JOB_PENDIENTE: p++; break;
            case HERA_JOB_TOMADO:    t++; break;
            case HERA_JOB_HECHO:     h++; break;
            case HERA_JOB_FALLIDO:   f++; break;
        }
    }
    const size_t total = g_jobs_n;
    desbloquear();

    /* Recuentos y nada más: ni mensaje, ni respuesta, ni motivo. El motivo
     * puede llevar dentro palabras de la persona, y la telemetría acaba en
     * sitios sin las reglas del almacén. */
    int n;
#if HERA_SABOTAJE == 32
    /* Sabotaje: la telemetría se lleva el texto del recuerdo. */
    bloquear(LOCK_SH);
    n = snprintf(out, cap,
                 "{\"total\":%zu,\"pendientes\":%zu,\"tomados\":%zu,"
                 "\"hechos\":%zu,\"fallidos\":%zu,\"ultimo\":\"%s\"}",
                 total, p, t, h, f, g_jobs_n ? g_jobs[0].mensaje : "");
    desbloquear();
#else
    n = snprintf(out, cap,
                 "{\"total\":%zu,\"pendientes\":%zu,\"tomados\":%zu,"
                 "\"hechos\":%zu,\"fallidos\":%zu}", total, p, t, h, f);
#endif
    return (n > 0) ? (size_t)n : 0;
}
