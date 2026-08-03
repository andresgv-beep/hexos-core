/*
 * HEXOS — registro durable de chats. Ver hexos_chats.h para la frontera.
 *
 * Mismo patrón que HERA: diario de solo añadir, estado derivado leyéndolo
 * entero, relectura + decisión + escritura dentro del mismo cerrojo. Se repite
 * porque funciona y porque tener dos formas distintas de persistir en el mismo
 * proyecto es una manera cara de equivocarse.
 */

#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif

#include "hexos_chats.h"

#include <errno.h>
#include <fcntl.h>
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/file.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>

#define LINEA_MAX (CHAT_TEXTO_MAX * 3)

static chat_t          g_chats[CHATS_MAX];
static size_t          g_chats_n;
static char            g_activo[CHAT_ID_MAX];
static char            g_ruta[1200];
static bool            g_abierto;
static int             g_lock_fd = -1;
static int             g_lock_prof;
static unsigned        g_seq;
static pthread_mutex_t g_mtx = PTHREAD_RECURSIVE_MUTEX_INITIALIZER_NP;

static void recargar(void);

static void bloquear(int op) {
    pthread_mutex_lock(&g_mtx);
    if (g_lock_prof++ == 0 && g_lock_fd >= 0)
        while (flock(g_lock_fd, op) != 0 && errno == EINTR) { }
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

static long long ahora(void) {
    const char *fijo = getenv("HEXOS_TS_FIJO");
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

static chat_t *buscar_mut(const char *id) {
    if (!id || !*id) return NULL;
    for (size_t i = 0; i < g_chats_n; i++)
        if (strcmp(g_chats[i].id, id) == 0) return &g_chats[i];
    return NULL;
}

static void soltar_lineas(chat_t *c) {
    for (size_t i = 0; i < c->lineas_n; i++) free(c->lineas[i].texto);
    c->lineas_n = 0;
}

/* ------------------------------------------------------------------------ */

static void aplicar(const char *linea) {
    char r[24], id[CHAT_ID_MAX];
    if (!campo(linea, "r", r, sizeof(r))) return;
    if (!campo(linea, "chat", id, sizeof(id))) return;

    if (strcmp(r, "creado") == 0) {
        if (buscar_mut(id) || g_chats_n >= CHATS_MAX) return;
        chat_t *c = &g_chats[g_chats_n++];
        memset(c, 0, sizeof(*c));
        snprintf(c->id, sizeof(c->id), "%s", id);
        campo(linea, "titulo", c->titulo, sizeof(c->titulo));
        c->creado = c->actualizado = numero(linea, "ts");
        unsigned n = 0;
        if (sscanf(id, "c%u", &n) == 1 && n > g_seq) g_seq = n;
        return;
    }
    chat_t *c = buscar_mut(id);
    if (!c) return;

    if (strcmp(r, "dicho") == 0) {
        if (c->lineas_n >= CHAT_LINEAS_MAX) {
            /* La transcripción tiene tope. Al pasarlo se pierde el turno más
             * viejo, y eso significa que reconstruir el KV ya no da el mismo
             * contexto. Es la deuda de compactación, no un detalle. */
            free(c->lineas[0].texto);
            memmove(&c->lineas[0], &c->lineas[1],
                    sizeof(chat_linea_t) * (CHAT_LINEAS_MAX - 1));
            c->lineas_n--;
        }
        chat_linea_t *l = &c->lineas[c->lineas_n];
        campo(linea, "rol", l->rol, sizeof(l->rol));
        char *t = malloc(CHAT_TEXTO_MAX);
        if (!t) return;
        t[0] = '\0';
        campo(linea, "texto", t, CHAT_TEXTO_MAX);
        l->texto = t;
        c->lineas_n++;
        c->actualizado = numero(linea, "ts");
        return;
    }
    if (strcmp(r, "titulo") == 0) {
        campo(linea, "titulo", c->titulo, sizeof(c->titulo));
        c->actualizado = numero(linea, "ts");
        return;
    }
    if (strcmp(r, "activo") == 0) {
        snprintf(g_activo, sizeof(g_activo), "%s", id);
        return;
    }
    if (strcmp(r, "borrado") == 0) {
        c->borrado = true;
        soltar_lineas(c);
        if (strcmp(g_activo, id) == 0) g_activo[0] = '\0';
        return;
    }
}

static void recargar(void) {
    for (size_t i = 0; i < g_chats_n; i++) soltar_lineas(&g_chats[i]);
    g_chats_n = 0;
    g_activo[0] = '\0';
    g_seq = 0;

    FILE *f = fopen(g_ruta, "r");
    if (!f) return;
    char *linea = malloc(LINEA_MAX);
    if (linea) {
        while (fgets(linea, LINEA_MAX, f)) {
            size_t l = strlen(linea);
            if (l == 0 || linea[l - 1] != '\n') break;   /* cola a medias */
            linea[--l] = '\0';
            if (l && linea[l - 1] == '}') aplicar(linea);
        }
        free(linea);
    }
    fclose(f);
    /* Ninguna sesión sobrevive a un arranque del motor: Héctor acaba de nacer.
     * Decir lo contrario sería prometer un KV que no existe, y el primer turno
     * lo descubriría contestando sin contexto. */
    for (size_t i = 0; i < g_chats_n; i++) g_chats[i].sesion_viva = false;
}

bool chats_abrir(void) {
    const char *custom = getenv("HELIOS_HOME");
    char dir[1024];
    if (custom && *custom) snprintf(dir, sizeof(dir), "%s", custom);
    else {
        const char *home = getenv("HOME");
        snprintf(dir, sizeof(dir), "%s/.helios", home ? home : ".");
    }
    mkdir(dir, 0755);
    snprintf(g_ruta, sizeof(g_ruta), "%s/chats.jsonl", dir);

    if (g_lock_fd < 0) {
        char rl[1200];
        snprintf(rl, sizeof(rl), "%s/chats.lock", dir);
        g_lock_fd = open(rl, O_RDWR | O_CREAT | O_CLOEXEC, 0644);
        if (g_lock_fd < 0) return false;
    }
    bloquear(LOCK_EX);
    FILE *f = fopen(g_ruta, "a");
    if (!f) { desbloquear(); return false; }
    fclose(f);
    recargar();
    desbloquear();
    g_abierto = true;
    return true;
}

void chats_cerrar(void) {
    g_abierto = false;
    for (size_t i = 0; i < g_chats_n; i++) soltar_lineas(&g_chats[i]);
    g_chats_n = 0;
    g_activo[0] = '\0';
    if (g_lock_fd >= 0) { close(g_lock_fd); g_lock_fd = -1; g_lock_prof = 0; }
}

/* ------------------------------------------------------------------------ */

bool chats_crear(const char *titulo, char *out_id, size_t cap) {
    if (!g_abierto) return false;
    bloquear(LOCK_EX);
    recargar();
    if (g_chats_n >= CHATS_MAX) { desbloquear(); return false; }

    char id[CHAT_ID_MAX];
    snprintf(id, sizeof(id), "c%u", g_seq + 1);
    char t[CHAT_TITULO_MAX * 2];
    esc(titulo && *titulo ? titulo : "Chat nuevo", t, sizeof(t));

    char linea[CHAT_TITULO_MAX * 3];
    snprintf(linea, sizeof(linea),
             "{\"r\":\"creado\",\"chat\":\"%s\",\"ts\":%lld,\"titulo\":\"%s\"}",
             id, ahora(), t);
    const bool ok = anexar(linea);
    if (ok) { aplicar(linea); if (out_id && cap) snprintf(out_id, cap, "%s", id); }
    desbloquear();
    return ok;
}

size_t chats_listar(const chat_t **out, size_t cap) {
    bloquear(LOCK_SH);
    size_t n = 0;
    /* Del más reciente al más viejo: el orden de la barra lateral. */
    for (;;) {
        long long mejor = -1;
        const chat_t *elegido = NULL;
        for (size_t i = 0; i < g_chats_n; i++) {
            const chat_t *c = &g_chats[i];
            if (c->borrado) continue;
            bool ya = false;
            for (size_t j = 0; j < n; j++) if (out[j] == c) ya = true;
            if (ya) continue;
            if (c->actualizado > mejor) { mejor = c->actualizado; elegido = c; }
        }
        if (!elegido || n >= cap) break;
        out[n++] = elegido;
    }
    desbloquear();
    return n;
}

const chat_t *chats_buscar(const char *id) {
    bloquear(LOCK_SH);
    chat_t *c = buscar_mut(id);
    if (c && c->borrado) c = NULL;
    desbloquear();
    return c;
}

bool chats_activar(const char *id) {
    if (!g_abierto) return false;
    bloquear(LOCK_EX);
    chat_t *c = buscar_mut(id);
    if (!c || c->borrado) { desbloquear(); return false; }
    char linea[CHAT_ID_MAX + 64];
    snprintf(linea, sizeof(linea),
             "{\"r\":\"activo\",\"chat\":\"%s\",\"ts\":%lld}", id, ahora());
    const bool ok = anexar(linea);
    /* Activar NO cierra el anterior: se queda pausado con su KV vivo. Es lo
     * que hace que volver sea seguir la conversación y no rehacerla. */
    if (ok) snprintf(g_activo, sizeof(g_activo), "%s", id);
    desbloquear();
    return ok;
}

const char *chats_activo(void) { return g_activo; }

bool chats_anotar(const char *id, const char *rol, const char *texto) {
    if (!g_abierto || !texto || !*texto) return false;
    if (strlen(texto) >= CHAT_TEXTO_MAX - 1) return false;
    bloquear(LOCK_EX);
    chat_t *c = buscar_mut(id);
    if (!c || c->borrado) { desbloquear(); return false; }

    char *e = malloc(CHAT_TEXTO_MAX * 2);
    char *linea = malloc(LINEA_MAX);
    if (!e || !linea) { free(e); free(linea); desbloquear(); return false; }
    esc(texto, e, CHAT_TEXTO_MAX * 2);
    snprintf(linea, LINEA_MAX,
             "{\"r\":\"dicho\",\"chat\":\"%s\",\"ts\":%lld,\"rol\":\"%s\","
             "\"texto\":\"%s\"}", id, ahora(), rol, e);
    const bool ok = anexar(linea);
    if (ok) aplicar(linea);
    free(e); free(linea);
    desbloquear();
    return ok;
}

void chats_marcar_sesion(const char *id, bool viva) {
    bloquear(LOCK_EX);
    chat_t *c = buscar_mut(id);
    if (c) c->sesion_viva = viva;
    desbloquear();
}

bool chats_sesion_viva(const char *id) {
    bloquear(LOCK_SH);
    const chat_t *c = buscar_mut(id);
    const bool v = c && !c->borrado && c->sesion_viva;
    desbloquear();
    return v;
}

bool chats_cerrar_sesion(const char *id) {
    bloquear(LOCK_EX);
    chat_t *c = buscar_mut(id);
    if (!c || c->borrado) { desbloquear(); return false; }
    /* Solo se apaga la bandera: la conversación se queda entera en el diario.
     * Cerrar libera memoria, no recuerdos. */
    c->sesion_viva = false;
    desbloquear();
    return true;
}

bool chats_borrar(const char *id) {
    if (!g_abierto) return false;
    bloquear(LOCK_EX);
    chat_t *c = buscar_mut(id);
    if (!c || c->borrado) { desbloquear(); return false; }
    char linea[CHAT_ID_MAX + 64];
    snprintf(linea, sizeof(linea),
             "{\"r\":\"borrado\",\"chat\":\"%s\",\"ts\":%lld}", id, ahora());
    const bool ok = anexar(linea);
    if (ok) aplicar(linea);
    desbloquear();
    return ok;
}

/* ------------------------------------------------------------------------ */

size_t chats_listar_json(char *out, size_t cap) {
    const chat_t *lista[CHATS_MAX];
    const size_t n = chats_listar(lista, CHATS_MAX);
    int w = snprintf(out, cap, "{\"activo\":\"%s\",\"chats\":[", g_activo);
    for (size_t i = 0; i < n && (size_t)w < cap; i++) {
        char t[CHAT_TITULO_MAX * 2];
        esc(lista[i]->titulo, t, sizeof(t));
        w += snprintf(out + w, cap - w,
                      "%s{\"id\":\"%s\",\"titulo\":\"%s\",\"creado\":%lld,"
                      "\"actualizado\":%lld,\"turnos\":%zu,\"sesion_viva\":%s}",
                      i ? "," : "", lista[i]->id, t, lista[i]->creado,
                      lista[i]->actualizado, lista[i]->lineas_n,
                      lista[i]->sesion_viva ? "true" : "false");
    }
    w += snprintf(out + w, cap - w, "]}");
    return (w > 0) ? (size_t)w : 0;
}

size_t chats_json(const char *id, char *out, size_t cap) {
    bloquear(LOCK_SH);
    const chat_t *c = buscar_mut(id);
    if (!c || c->borrado) { desbloquear(); return 0; }
    char t[CHAT_TITULO_MAX * 2];
    esc(c->titulo, t, sizeof(t));
    int w = snprintf(out, cap,
                     "{\"id\":\"%s\",\"titulo\":\"%s\",\"sesion_viva\":%s,"
                     "\"turnos\":[", c->id, t, c->sesion_viva ? "true" : "false");
    char *e = malloc(CHAT_TEXTO_MAX * 2);
    for (size_t i = 0; e && i < c->lineas_n && (size_t)w + 64 < cap; i++) {
        esc(c->lineas[i].texto ? c->lineas[i].texto : "", e, CHAT_TEXTO_MAX * 2);
        w += snprintf(out + w, cap - w, "%s{\"rol\":\"%s\",\"texto\":\"%s\"}",
                      i ? "," : "", c->lineas[i].rol, e);
    }
    free(e);
    w += snprintf(out + w, cap - w, "]}");
    desbloquear();
    return (w > 0) ? (size_t)w : 0;
}
