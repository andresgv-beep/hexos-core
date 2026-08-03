/*
 * HERA — almacén de memoria (E3)
 *
 * Ver hera_store.h para las cuatro reglas. Aquí solo el cómo.
 *
 * El diario es JSONL de solo añadir. Cada línea es un registro:
 *
 *   {"r":"dijo","id":"u1","ts":...,"texto":"mi perro se llama Byteazul"}
 *   {"r":"hecho","id":"f1","ts":...,"clave":"perro/nombre","valor":"Byteazul",
 *    "texto":"Su perro se llama Byteazul","estado":"candidato",
 *    "evidencia":"u1","confirmacion":"","origen":"modelo"}
 *   {"r":"confirma","id":"f1","por":"u5","ts":...}
 *   {"r":"corrige","viejo":"f1","id":"f2",...}     <- UNA línea, no dos
 *   {"r":"importado","ts":...,"n":3}
 *
 * ATOMICIDAD. Una corrección es un solo registro. Al releer se descarta toda
 * línea que no venga terminada en '\n' y en '}': si el proceso murió a mitad
 * de escribirla, esa línea está incompleta, se tira entera y el estado sigue
 * siendo el de antes de intentarlo. Lo que no puede pasar es que sobreviva la
 * mitad que crea el hecho nuevo sin la mitad que jubila al viejo — que es lo
 * que dejaría dos confirmados contradiciéndose.
 *
 * El estado vive en RAM y se reconstruye leyendo el fichero entero al abrir.
 * Son decenas o cientos de líneas por perfil: releerlas cuesta menos que
 * mantener un índice que se pueda desincronizar del diario.
 */

#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif

#include "hera_store.h"

#include <ctype.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <fcntl.h>
#include <pthread.h>
#include <sys/file.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>

#define HECHOS_MAX     4096
#define DICHOS_MAX     4096
/* Holgada a proposito: el registro mas largo que se escribe es un "dijo" con
 * HERA_UTTER_MAX de texto escapado, ~8 KB. El buffer tiene que superarlo con
 * margen porque una lectura que LLENA el buffer sin ver '\n' es
 * indistinguible de una cola incompleta, y confundirlas truncaria datos
 * validos. */
#define LINEA_MAX      (HERA_UTTER_MAX * 4)

typedef struct {
    char id[HERA_ID_MAX];
    char texto[HERA_UTTER_MAX];
} dicho_t;

static hera_hecho_t g_hechos[HECHOS_MAX];
static size_t       g_hechos_n;
static dicho_t      g_dichos[DICHOS_MAX];
static size_t       g_dichos_n;
static char         g_ruta[1200];
static bool         g_abierto;
static bool         g_importado;
static unsigned     g_seq_u, g_seq_f;

/* ------------------------------------------------------------------------
 * CERROJO. El diario es multiproceso: lo tocan HexOS y la CLI a la vez, y
 * puede que mañana un demonio de consolidación. Sin exclusión, la secuencia
 * inocente "releo, veo u10, escribo u11" se cruza:
 *
 *   HexOS lee (último u10)      hera lee (último u10)
 *   HexOS calcula u11           hera calcula u11
 *   HexOS escribe u11           hera escribe u11
 *
 * y quedan DOS evidencias distintas con el mismo id. Después una corrección
 * cita "u11" y se lleva las palabras equivocadas — precisamente la clase de
 * fallo que todo este almacén existe para hacer imposible.
 *
 * DOS CAPAS, porque hacen falta las dos:
 *   · flock sobre `hera.lock` excluye entre PROCESOS. Fichero aparte y no el
 *     propio diario, para que el truncado de la cola no se pelee con él.
 *   · un mutex recursivo excluye entre HILOS del mismo proceso: flock se
 *     concede por descriptor abierto, así que dos hilos de HexOS lo
 *     "tendrían" los dos a la vez y no se excluirían en absoluto.
 *
 * Todo lo que muta hace RELECTURA + VALIDACIÓN + ID + APPEND dentro del mismo
 * cerrojo exclusivo. Partirlo en dos tramos es tener la carrera otra vez.
 * ------------------------------------------------------------------------ */
static int             g_lock_fd = -1;
static int             g_lock_prof;
static pthread_mutex_t g_mtx = PTHREAD_RECURSIVE_MUTEX_INITIALIZER_NP;

static void recargar(bool puede_reparar);

static void bloquear(int op) {
    pthread_mutex_lock(&g_mtx);
#if HERA_SABOTAJE == 10
    /* Sabotaje: sin exclusión entre procesos. Dos que releen a la vez calculan
     * el mismo id siguiente y los dos lo escriben. */
    (void)op; g_lock_prof++; return;
#endif
    if (g_lock_prof++ == 0 && g_lock_fd >= 0) {
        while (flock(g_lock_fd, op) != 0 && errno == EINTR) { }
    }
}

static void desbloquear(void) {
#if HERA_SABOTAJE == 10
    g_lock_prof--; pthread_mutex_unlock(&g_mtx); return;
#endif
    if (--g_lock_prof == 0 && g_lock_fd >= 0) flock(g_lock_fd, LOCK_UN);
    pthread_mutex_unlock(&g_mtx);
}

const char *hera_veredicto_nombre(hera_veredicto_t v) {
    switch (v) {
        case HERA_OK:                       return "ok";
        case HERA_RECHAZO_SIN_EVIDENCIA:    return "sin_evidencia";
        case HERA_RECHAZO_NO_LITERAL:       return "no_literal";
        case HERA_RECHAZO_SUJETO_AJENO:     return "sujeto_ajeno";
        case HERA_RECHAZO_POLARIDAD:        return "polaridad";
        case HERA_RECHAZO_SIN_CONFIRMACION: return "sin_confirmacion";
        case HERA_RECHAZO_DUPLICADO:        return "duplicado";
        case HERA_RECHAZO_INVALIDO:         return "invalido";
        case HERA_RECHAZO_DESCONOCIDO:      return "desconocido";
    }
    return "?";
}

const char *hera_estado_nombre(hera_estado_t e) {
    switch (e) {
        case HERA_CANDIDATO:  return "candidato";
        case HERA_CONFIRMADO: return "confirmado";
        case HERA_SUSTITUIDO: return "sustituido";
    }
    return "?";
}

/* ------------------------------------------------------------------------
 * Normalización. Minúsculas ASCII y todo lo que no sea letra o número pasa a
 * separador. Los bytes >= 128 se dejan intactos: pasarlos por tolower() con
 * locale "C" no hace nada, y tocarlos byte a byte partiría un UTF-8 de dos
 * bytes por la mitad. "Bilbao" y "bilbao" casan; "Bilbaó" y "Bilbao" no, y eso
 * es correcto — un acento distinto es otra palabra hasta que se demuestre lo
 * contrario.
 * ------------------------------------------------------------------------ */
static void normalizar(const char *in, char *out, size_t cap) {
    size_t o = 0;
    for (const unsigned char *p = (const unsigned char *)in; *p && o + 1 < cap; p++) {
        if (*p >= 128)                 out[o++] = (char)*p;
        else if (isalnum(*p))          out[o++] = (char)tolower(*p);
        else                           out[o++] = ' ';
    }
    out[o] = '\0';
}

/* Palabra completa dentro de un texto ya normalizado. Sin esto "Ana" colaría
 * dentro de "manzana". */
static bool tiene_palabra(const char *texto_norm, const char *palabra) {
    const size_t l = strlen(palabra);
    if (!l) return false;
    for (const char *p = strstr(texto_norm, palabra); p;
         p = strstr(p + 1, palabra)) {
        const bool ini = (p == texto_norm) || p[-1] == ' ';
        const bool fin = (p[l] == '\0') || p[l] == ' ';
        if (ini && fin) return true;
    }
    return false;
}

/* ------------------------------------------------------------------------
 * POLARIDAD. La comprobación por bolsa de palabras pierde las negaciones
 * cortas: "no" tiene dos letras y se cae de cualquier filtro por longitud, así
 * que "me gusta el café" autorizaba "no me gusta el café" — el hecho exacto
 * del revés. Se compara la PRESENCIA de negación en el valor contra la de la
 * frase citada, y tienen que coincidir.
 *
 * Es una comprobación deliberadamente burda y rechaza de más: en "no tengo
 * perro pero me gusta el café", el valor "me gusta el café" se rechaza porque
 * la frase contiene un "no" que era de otra cosa. Se acepta ese coste. Un
 * rechazo de más significa que el dato no se guarda solo y la persona puede
 * pedirlo a mano; un rechazo de menos significa guardar lo contrario de lo que
 * dijo y repetírselo mañana como si lo hubiera dicho ella.
 * ------------------------------------------------------------------------ */
static bool hay_negacion(const char *texto_norm) {
    static const char *marcas[] = {"no", "nunca", "jamas", "jamás", "tampoco",
                                   "ni", "sin", NULL};
    for (int i = 0; marcas[i]; i++)
        if (tiene_palabra(texto_norm, marcas[i])) return true;
    return false;
}

/* Sujeto de una clave "sujeto/predicado". */
static void sujeto_de(const char *clave, char *out, size_t cap) {
    const char *barra = strchr(clave, '/');
    const size_t n = barra ? (size_t)(barra - clave) : strlen(clave);
    const size_t c = (n < cap - 1) ? n : cap - 1;
    memcpy(out, clave, c);
    out[c] = '\0';
}

/* ------------------------------------------------------------------------
 * La comprobación de fondo: ¿respalda esta frase este hecho?
 *
 * Se exige que TODO ocurra en la MISMA frase — sujeto, valor y polaridad. Sin
 * el troceo por frases, "Ana es mi hermana. Luis vive en Bilbao" respaldaría
 * `ana/ciudad = Bilbao`: las dos palabras están en el texto, solo que hablando
 * de personas distintas. Atribuirle a uno lo que se dijo de otro es el mismo
 * fallo que la regla 1 quería impedir, un nivel más abajo.
 * ------------------------------------------------------------------------ */
static hera_veredicto_t frase_respalda(const char *frase_norm,
                                       const char *sujeto_norm,
                                       const char *valor_norm,
                                       bool sujeto_es_yo) {
#if HERA_SABOTAJE == 1
    /* Sabotaje: la comprobación de respaldo siempre dice que sí. */
    (void)frase_norm; (void)sujeto_norm; (void)valor_norm; (void)sujeto_es_yo;
    return HERA_OK;
#elif HERA_SABOTAJE == 4
    /* Sabotaje: se comprueba el dato pero no de quién se dijo — el fallo
     * "Luis vive en Bilbao autoriza ana/ciudad = Bilbao". */
    sujeto_es_yo = true;
#endif
    /* 1. Sujeto. "yo" no necesita estar escrito: quien dice "vivo en Sevilla"
     *    no se nombra, pero es el autor del texto y eso lo acredita. */
    if (!sujeto_es_yo && !tiene_palabra(frase_norm, sujeto_norm))
        return HERA_RECHAZO_SUJETO_AJENO;

    /* 2. Valor, palabra a palabra. Las de una o dos letras no se exigen: no
     *    aportan y pedirlas rechazaría hechos legítimos. */
    bool alguna = false;
    char copia[HERA_VALOR_MAX * 2];
    snprintf(copia, sizeof(copia), "%s", valor_norm);
    for (char *tok = strtok(copia, " "); tok; tok = strtok(NULL, " ")) {
        if (strlen(tok) < 3) continue;
        alguna = true;
        if (!tiene_palabra(frase_norm, tok)) return HERA_RECHAZO_NO_LITERAL;
    }
    /* Un valor sin ninguna palabra significativa ("42", "sí") no se puede
     * verificar así: se exige entero como subcadena. */
    if (!alguna && !strstr(frase_norm, valor_norm))
        return HERA_RECHAZO_NO_LITERAL;

    /* 3. Polaridad. */
#if HERA_SABOTAJE == 5
    /* Sabotaje: bolsa de palabras pura, la negación corta se pierde. */
    return HERA_OK;
#endif
    if (hay_negacion(valor_norm) != hay_negacion(frase_norm))
        return HERA_RECHAZO_POLARIDAD;

    return HERA_OK;
}

/* Recorre las frases del texto citado y devuelve OK si alguna respalda el
 * hecho. Si ninguna lo hace, devuelve el rechazo MÁS ESPECÍFICO que se haya
 * visto: saber que el sujeto era otro es más útil que un "no_literal" genérico
 * cuando estás depurando por qué no se guardó algo. */
static hera_veredicto_t texto_respalda(const char *texto, const char *clave,
                                       const char *valor) {
    char sujeto[HERA_CLAVE_MAX], sujeto_norm[HERA_CLAVE_MAX * 2];
    sujeto_de(clave, sujeto, sizeof(sujeto));
    normalizar(sujeto, sujeto_norm, sizeof(sujeto_norm));
    const bool es_yo = (strcmp(sujeto, HERA_SUJETO_YO) == 0);

    char valor_norm[HERA_VALOR_MAX * 2];
    normalizar(valor, valor_norm, sizeof(valor_norm));

    hera_veredicto_t peor = HERA_RECHAZO_NO_LITERAL;
    const char *ini = texto;
    while (*ini) {
        size_t n = strcspn(ini, ".;!?\n");
        if (n > 0) {
            char frase[HERA_UTTER_MAX];
            const size_t c = (n < sizeof(frase) - 1) ? n : sizeof(frase) - 1;
            memcpy(frase, ini, c);
            frase[c] = '\0';

            char frase_norm[HERA_UTTER_MAX * 2];
            normalizar(frase, frase_norm, sizeof(frase_norm));
            const hera_veredicto_t v =
                frase_respalda(frase_norm, sujeto_norm, valor_norm, es_yo);
            if (v == HERA_OK) return HERA_OK;
            /* Sujeto correcto pero polaridad o dato mal: más informativo. */
            if (v == HERA_RECHAZO_POLARIDAD) peor = v;
            else if (v == HERA_RECHAZO_SUJETO_AJENO &&
                     peor == HERA_RECHAZO_NO_LITERAL) peor = v;
        }
        ini += n;
        while (*ini && strchr(".;!?\n", *ini)) ini++;
    }
    return peor;
}

/* Duplicado: mismo valor normalizado bajo la misma clave, entre lo vigente. */
static bool es_duplicado(const char *clave, const char *valor) {
    for (size_t i = 0; i < g_hechos_n; i++) {
        if (g_hechos[i].estado == HERA_SUSTITUIDO) continue;
        if (strcmp(g_hechos[i].clave, clave) != 0) continue;
        char a[HERA_VALOR_MAX * 2], b[HERA_VALOR_MAX * 2];
        normalizar(valor, a, sizeof(a));
        normalizar(g_hechos[i].valor, b, sizeof(b));
        if (strcmp(a, b) == 0) return true;
    }
    return false;
}

/* ------------------------------------------------------------------------
 * JSON mínimo
 * ------------------------------------------------------------------------ */

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

static bool leer_campo(const char *linea, const char *clave,
                       char *out, size_t cap) {
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

/* ------------------------------------------------------------------------
 * Perfil y diario
 * ------------------------------------------------------------------------ */

static void directorio(char *out, size_t cap) {
    const char *custom = getenv("HELIOS_HOME");
    if (custom && *custom) snprintf(out, cap, "%s", custom);
    else {
        const char *home = getenv("HOME");
        snprintf(out, cap, "%s/.helios", home ? home : ".");
    }
    mkdir(out, 0755);
}

/* Reloj fijable para que las pruebas puedan comparar diarios byte a byte. */
static long long ahora(void) {
    const char *fijo = getenv("HERA_TS_FIJO");
    if (fijo && *fijo) return atoll(fijo);
    return (long long)time(NULL);
}

/* Una escritura, un registro. El fichero se abre en modo añadir y se cierra
 * en cada llamada: si el proceso cae, cae entre registros, no dentro de uno
 * a medio vaciar del buffer. */
static bool anexar(const char *linea) {
    FILE *f = fopen(g_ruta, "a");
    if (!f) return false;
    const size_t l = strlen(linea);
    const bool ok = fwrite(linea, 1, l, f) == l && fputc('\n', f) != EOF;
    return (fclose(f) == 0) && ok;
}

static hera_hecho_t *buscar_hecho(const char *id) {
    for (size_t i = 0; i < g_hechos_n; i++)
        if (strcmp(g_hechos[i].id, id) == 0) return &g_hechos[i];
    return NULL;
}

static hera_hecho_t *vigente(const char *clave) {
    for (size_t i = g_hechos_n; i > 0; i--) {
        hera_hecho_t *h = &g_hechos[i - 1];
        if (h->estado == HERA_CONFIRMADO && strcmp(h->clave, clave) == 0)
            return h;
    }
    return NULL;
}

/* Posición cronológica de una intervención; -1 si no existe. El diario es de
 * solo añadir, así que el orden del array ES el orden en que se dijeron. */
static int indice_dicho(const char *id) {
    if (!id || !*id) return -1;
    for (size_t i = 0; i < g_dichos_n; i++)
        if (strcmp(g_dichos[i].id, id) == 0) return (int)i;
    return -1;
}

/* Sin cerrojo: se llama desde dentro de regiones ya bloqueadas. */
static const char *evidencia_interna(const char *id) {
    if (!id || !*id) return NULL;
    for (size_t i = 0; i < g_dichos_n; i++)
        if (strcmp(g_dichos[i].id, id) == 0) return g_dichos[i].texto;
    return NULL;
}

const char *hera_store_evidencia(const char *id) {
    bloquear(LOCK_SH);
    recargar(false);
    const char *r = evidencia_interna(id);
    desbloquear();
    return r;
}

const char *hera_store_ruta(void) { return g_ruta; }

/* ------------------------------------------------------------------------
 * Relectura
 * ------------------------------------------------------------------------ */

/* Alta en RAM de un hecho leído o recién escrito. */
static hera_hecho_t *poner_en_ram(const char *id, const char *clave,
                                  const char *valor, const char *texto,
                                  hera_estado_t estado, const char *evidencia,
                                  const char *confirmacion, const char *origen,
                                  long long ts) {
    if (g_hechos_n >= HECHOS_MAX) return NULL;
    hera_hecho_t *h = &g_hechos[g_hechos_n++];
    memset(h, 0, sizeof(*h));
    snprintf(h->id, sizeof(h->id), "%s", id);
    snprintf(h->clave, sizeof(h->clave), "%s", clave);
    snprintf(h->valor, sizeof(h->valor), "%s", valor);
    snprintf(h->texto, sizeof(h->texto), "%s", texto);
    snprintf(h->evidencia, sizeof(h->evidencia), "%s", evidencia ? evidencia : "");
    snprintf(h->confirmacion, sizeof(h->confirmacion), "%s",
             confirmacion ? confirmacion : "");
    snprintf(h->origen, sizeof(h->origen), "%s", origen);
    h->estado = estado;
    h->ts = ts;
    unsigned n = 0;
    if (sscanf(id, "f%u", &n) == 1 && n > g_seq_f) g_seq_f = n;
    return h;
}

static void aplicar(const char *linea) {
    char r[32];
    if (!leer_campo(linea, "r", r, sizeof(r))) return;

    if (strcmp(r, "dijo") == 0) {
        if (g_dichos_n >= DICHOS_MAX) return;
        dicho_t *d = &g_dichos[g_dichos_n];
        if (!leer_campo(linea, "id", d->id, sizeof(d->id))) return;
        d->texto[0] = '\0';
        leer_campo(linea, "texto", d->texto, sizeof(d->texto));
        unsigned n = 0;
        if (sscanf(d->id, "u%u", &n) == 1 && n > g_seq_u) g_seq_u = n;
        g_dichos_n++;
        return;
    }

    if (strcmp(r, "hecho") == 0 || strcmp(r, "corrige") == 0) {
        char id[HERA_ID_MAX], clave[HERA_CLAVE_MAX], valor[HERA_VALOR_MAX];
        char texto[HERA_TEXTO_MAX], ev[HERA_ID_MAX] = "", cf[HERA_ID_MAX] = "";
        char origen[16] = "modelo", est[24] = "candidato";
        if (!leer_campo(linea, "id", id, sizeof(id))) return;
        if (!leer_campo(linea, "clave", clave, sizeof(clave))) return;
        if (!leer_campo(linea, "valor", valor, sizeof(valor))) return;
        if (!leer_campo(linea, "texto", texto, sizeof(texto)))
            snprintf(texto, sizeof(texto), "%s", valor);
        leer_campo(linea, "evidencia", ev, sizeof(ev));
        leer_campo(linea, "confirmacion", cf, sizeof(cf));
        leer_campo(linea, "origen", origen, sizeof(origen));
        leer_campo(linea, "estado", est, sizeof(est));
        const char *ts = strstr(linea, "\"ts\":");

        const hera_estado_t estado =
            (strcmp(r, "corrige") == 0 || strcmp(est, "confirmado") == 0)
                ? HERA_CONFIRMADO : HERA_CANDIDATO;
        poner_en_ram(id, clave, valor, texto, estado, ev, cf, origen,
                     ts ? atoll(ts + 5) : 0);

        /* La corrección jubila al viejo en el MISMO registro. Si esta línea
         * hubiera quedado a medias no habríamos llegado hasta aquí: la
         * relectura la habría descartado entera. */
        if (strcmp(r, "corrige") == 0) {
            char viejo[HERA_ID_MAX];
            if (leer_campo(linea, "viejo", viejo, sizeof(viejo))) {
                hera_hecho_t *v = buscar_hecho(viejo);
                if (v) {
                    v->estado = HERA_SUSTITUIDO;
                    snprintf(v->sustituido_por, sizeof(v->sustituido_por),
                             "%s", id);
                }
            }
        }
        return;
    }

    if (strcmp(r, "confirma") == 0) {
        char id[HERA_ID_MAX], por[HERA_ID_MAX] = "";
        if (!leer_campo(linea, "id", id, sizeof(id))) return;
        leer_campo(linea, "por", por, sizeof(por));
        hera_hecho_t *h = buscar_hecho(id);
        if (h && h->estado == HERA_CANDIDATO) {
            h->estado = HERA_CONFIRMADO;
            snprintf(h->confirmacion, sizeof(h->confirmacion), "%s", por);
        }
        return;
    }

    /* Registro suelto de sustitución: ya no se emite (la corrección es un
     * único evento), pero el lector lo entiende — es lo que permite que el
     * sabotaje 2 reviva el bug de las dos escrituras y la batería lo cace. */
    if (strcmp(r, "sustituye") == 0) {
        char viejo[HERA_ID_MAX], nuevo[HERA_ID_MAX];
        if (!leer_campo(linea, "viejo", viejo, sizeof(viejo))) return;
        if (!leer_campo(linea, "nuevo", nuevo, sizeof(nuevo))) return;
        hera_hecho_t *h = buscar_hecho(viejo);
        if (h) {
            h->estado = HERA_SUSTITUIDO;
            snprintf(h->sustituido_por, sizeof(h->sustituido_por), "%s", nuevo);
        }
        return;
    }

    if (strcmp(r, "importado") == 0) g_importado = true;
}

/* Relectura del diario. `puede_reparar` SOLO puede venir a true con el
 * cerrojo EXCLUSIVO tomado: truncar la cola mientras otro proceso está a
 * medio escribirla es peor que la cola. Un lector con cerrojo compartido la
 * ignora y se va sin tocar el fichero. */
static void recargar(bool puede_reparar) {
    g_hechos_n = g_dichos_n = 0;
    g_seq_u = g_seq_f = 0;
    g_importado = false;

    FILE *f = fopen(g_ruta, "r");
    if (!f) return;

    char *linea = malloc(LINEA_MAX);
    long fin_valido = 0;
    bool cola_incompleta = false;
    if (linea) {
        while (fgets(linea, LINEA_MAX, f)) {
            size_t l = strlen(linea);
            /* Registro completo = terminado en '\n'. Una línea sin salto solo
             * puede ser la última: alguien murió escribiéndola. */
            if (l == 0 || linea[l - 1] != '\n') {
                /* Salvo que haya llenado el buffer: entonces no es una cola,
                 * es una línea más larga de lo previsto, y truncar ahí se
                 * comería registros buenos. Se para sin tocar nada. */
                cola_incompleta = (l < LINEA_MAX - 1);
                break;
            }
            fin_valido += (long)l;
            linea[--l] = '\0';
            while (l && (linea[l - 1] == ' ' || linea[l - 1] == '\r'))
                linea[--l] = '\0';
            /* Línea entera pero mal formada: no se aplica, pero SÍ cuenta como
             * escritura terminada — recortar por delante de ella se llevaría
             * todo lo que vino después. */
            if (l == 0 || linea[l - 1] != '}') continue;
            aplicar(linea);
        }
        free(linea);
    }
    const long tam = (fseek(f, 0, SEEK_END) == 0) ? ftell(f) : fin_valido;
    fclose(f);

#if HERA_SABOTAJE == 9
    cola_incompleta = false;
#endif
    /* Ignorar la cola no basta: la siguiente escritura se pegaría detrás y en
     * el reinicio siguiente esa mezcla se leería como un registro terminado.
     * Se borra del disco — pero solo si mandamos nosotros. */
    if (puede_reparar && cola_incompleta && tam > fin_valido) {
        if (truncate(g_ruta, fin_valido) != 0) {
            /* Si no se puede reparar, mejor no fingir que el diario está
             * sano: se deja el estado leído y el fichero como está. */
            fprintf(stderr, "[hera] no pude reparar la cola de %s\n", g_ruta);
        }
    }
}

bool hera_store_abrir(void) {
    char dir[1024];
    directorio(dir, sizeof(dir));
    snprintf(g_ruta, sizeof(g_ruta), "%s/hera.jsonl", dir);

    /* El cerrojo va en su propio fichero: si compartiera el del diario, el
     * truncado de la cola estaría peleándose con el mismo descriptor que
     * sostiene la exclusión. */
    if (g_lock_fd < 0) {
        char ruta_lock[1200];
        snprintf(ruta_lock, sizeof(ruta_lock), "%s/hera.lock", dir);
        g_lock_fd = open(ruta_lock, O_RDWR | O_CREAT | O_CLOEXEC, 0644);
        if (g_lock_fd < 0) return false;
    }

    bloquear(LOCK_EX);
    FILE *f = fopen(g_ruta, "a");   /* crearlo ya: fallar aquí, no a mitad */
    if (!f) { desbloquear(); return false; }
    fclose(f);
    recargar(true);
    desbloquear();

    g_abierto = true;
    return true;
}

void hera_store_cerrar(void) {
    g_abierto = false;
    if (g_lock_fd >= 0) { close(g_lock_fd); g_lock_fd = -1; g_lock_prof = 0; }
    g_hechos_n = g_dichos_n = 0;
    g_ruta[0] = '\0';
}

/* ------------------------------------------------------------------------
 * Escritura
 * ------------------------------------------------------------------------ */

bool hera_store_dijo(const char *texto, char *out_id, size_t cap) {
    if (!g_abierto || !texto || !*texto) return false;

    /* RELECTURA + ID + APPEND en el MISMO cerrojo exclusivo. Si se releyera
     * fuera, otro proceso podría escribir entre medias y los dos usarían el
     * mismo id. */
    bloquear(LOCK_EX);
    recargar(true);
    if (g_dichos_n >= DICHOS_MAX) { desbloquear(); return false; }

    char id[HERA_ID_MAX];
    snprintf(id, sizeof(id), "u%u", ++g_seq_u);

    char e[HERA_UTTER_MAX * 2];
    esc(texto, e, sizeof(e));
    char linea[HERA_UTTER_MAX * 2 + 128];
    snprintf(linea, sizeof(linea),
             "{\"r\":\"dijo\",\"id\":\"%s\",\"ts\":%lld,\"texto\":\"%s\"}",
             id, ahora(), e);
    if (!anexar(linea)) { desbloquear(); return false; }

    dicho_t *d = &g_dichos[g_dichos_n++];
    snprintf(d->id, sizeof(d->id), "%s", id);
    snprintf(d->texto, sizeof(d->texto), "%s", texto);
    if (out_id && cap) snprintf(out_id, cap, "%s", id);
    desbloquear();
    return true;
}

/* La puerta única de validación. Todo lo que nazca aquí trae cita comprobada
 * sobre una frase entera: sujeto, dato y polaridad. */
static hera_veredicto_t validar(const char *clave, const char *valor,
                                const char *evidencia_id) {
    if (!g_abierto) return HERA_RECHAZO_INVALIDO;
    if (!clave || !*clave || !valor || !*valor) return HERA_RECHAZO_INVALIDO;
    if (strlen(clave) >= HERA_CLAVE_MAX || strlen(valor) >= HERA_VALOR_MAX)
        return HERA_RECHAZO_INVALIDO;

    const char *dicho = evidencia_interna(evidencia_id);
    if (!dicho) return HERA_RECHAZO_SIN_EVIDENCIA;
    return texto_respalda(dicho, clave, valor);
}

/* Escribe el registro de un hecho nuevo. `viejo_id` != NULL lo convierte en un
 * registro de CORRECCIÓN: una sola línea que crea y jubila a la vez. */
static hera_veredicto_t alta(const char *clave, const char *valor,
                             const char *texto, const char *evidencia_id,
                             const char *confirmacion_id, bool confirmado,
                             const char *origen, const char *viejo_id,
                             char *out_id, size_t cap) {
    if (g_hechos_n >= HECHOS_MAX) return HERA_RECHAZO_INVALIDO;

    char id[HERA_ID_MAX];
    snprintf(id, sizeof(id), "f%u", g_seq_f + 1);

    char ec[HERA_CLAVE_MAX * 2], ev[HERA_VALOR_MAX * 2], et[HERA_TEXTO_MAX * 2];
    esc(clave, ec, sizeof(ec));
    esc(valor, ev, sizeof(ev));
    esc(texto && *texto ? texto : valor, et, sizeof(et));

    char viejo_campo[64] = "";
    if (viejo_id) snprintf(viejo_campo, sizeof(viejo_campo),
                           "\"viejo\":\"%s\",", viejo_id);

    const long long ts = ahora();
    char linea[HERA_TEXTO_MAX * 4];
    snprintf(linea, sizeof(linea),
             "{\"r\":\"%s\",%s\"id\":\"%s\",\"ts\":%lld,\"clave\":\"%s\","
             "\"valor\":\"%s\",\"texto\":\"%s\",\"estado\":\"%s\","
             "\"evidencia\":\"%s\",\"confirmacion\":\"%s\",\"origen\":\"%s\"}",
             viejo_id ? "corrige" : "hecho", viejo_campo, id, ts, ec, ev, et,
             confirmado ? "confirmado" : "candidato",
             evidencia_id ? evidencia_id : "",
             confirmacion_id ? confirmacion_id : "", origen);
    if (!anexar(linea)) return HERA_RECHAZO_INVALIDO;

    /* Solo después de que el registro esté en disco se toca el estado en RAM:
     * si la escritura falla, la memoria no se ha creído nada. */
    poner_en_ram(id, clave, valor, texto && *texto ? texto : valor,
                 confirmado ? HERA_CONFIRMADO : HERA_CANDIDATO,
                 evidencia_id, confirmacion_id, origen, ts);

    if (viejo_id) {
        hera_hecho_t *v = buscar_hecho(viejo_id);
        if (v) {
            v->estado = HERA_SUSTITUIDO;
            snprintf(v->sustituido_por, sizeof(v->sustituido_por), "%s", id);
        }
    }
    if (out_id && cap) snprintf(out_id, cap, "%s", id);
    return HERA_OK;
}

/* ------------------------------------------------------------------------
 * Las cuatro operaciones, con bandera de ENSAYO.
 *
 * El ensayo recorre EXACTAMENTE las mismas comprobaciones y se para justo
 * antes de escribir. Comparten camino a propósito: una función de validación
 * escrita aparte acabaría divergiendo de la de verdad, y entonces el ensayo
 * diría que sí a cosas que el almacén rechaza — o peor, al revés.
 * ------------------------------------------------------------------------ */

static hera_veredicto_t proponer_impl(const char *clave, const char *valor,
                                      const char *texto,
                                      const char *evidencia_id,
                                      bool ensayo, char *out_id, size_t cap) {
    const hera_veredicto_t v = validar(clave, valor, evidencia_id);
    if (v != HERA_OK) return v;
    if (es_duplicado(clave, valor)) return HERA_RECHAZO_DUPLICADO;
    if (ensayo) return HERA_OK;
    /* Sin parámetro para nacer confirmado: por aquí no se asciende nada. */
    return alta(clave, valor, texto, evidencia_id, NULL, false, "modelo",
                NULL, out_id, cap);
}

hera_veredicto_t hera_store_proponer(const char *clave, const char *valor,
                                     const char *texto,
                                     const char *evidencia_id,
                                     char *out_id, size_t cap) {
    bloquear(LOCK_EX);
    recargar(true);
    const hera_veredicto_t v =
        proponer_impl(clave, valor, texto, evidencia_id, false, out_id, cap);
    desbloquear();
    return v;
}

hera_veredicto_t hera_store_registrar(const char *clave, const char *valor,
                                      const char *texto,
                                      const char *evidencia_id,
                                      const char *confirmacion_id,
                                      char *out_id, size_t cap) {
    bloquear(LOCK_EX);
    recargar(true);
    hera_veredicto_t v = HERA_OK;
    if (!evidencia_interna(confirmacion_id))
        v = HERA_RECHAZO_SIN_CONFIRMACION;
    else if ((v = validar(clave, valor, evidencia_id)) != HERA_OK) { /* ya está */ }
    else if (es_duplicado(clave, valor))
        v = HERA_RECHAZO_DUPLICADO;
    else
        v = alta(clave, valor, texto, evidencia_id, confirmacion_id, true,
                 "persona", NULL, out_id, cap);
    desbloquear();
    return v;
}

static hera_veredicto_t confirmar_impl(const char *id,
                                       const char *confirmacion_id,
                                       bool ensayo) {
    if (!g_abierto || !id || !*id) return HERA_RECHAZO_INVALIDO;
    /* Explícito y por delante de todo: sin esto, la seguridad frente a NULL
     * dependía de que la comprobación de evidencia se hiciera antes, y basta
     * reordenarlas para convertir un rechazo en un segfault. */
    if (!confirmacion_id || !*confirmacion_id)
        return HERA_RECHAZO_SIN_CONFIRMACION;
    /* La confirmación tiene que ser una intervención registrada de la persona.
     * Sin esto, "confirmado" solo querría decir "alguien llamó a esta función",
     * y una extracción del modelo podría ascenderse a sí misma. */
#if HERA_SABOTAJE != 6
    if (!evidencia_interna(confirmacion_id))
        return HERA_RECHAZO_SIN_CONFIRMACION;
#endif
    /* Sabotaje 6: confirmar sin que conste que la persona dijo nada — una
     * extracción del modelo podría ascenderse a sí misma. */

    hera_hecho_t *h = buscar_hecho(id);
    if (!h || h->estado == HERA_SUSTITUIDO) return HERA_RECHAZO_DESCONOCIDO;
    if (h->estado == HERA_CONFIRMADO) return HERA_OK;

#if HERA_SABOTAJE != 8 && HERA_SABOTAJE != 6
    /* La confirmación tiene que ser DISTINTA y POSTERIOR a lo que originó el
     * candidato. Aceptar la misma frase sería contarse a sí mismo: de "creo
     * que me mudo a Girona" saldría el candidato Y su confirmación, y una
     * extracción del modelo se quedaría confirmada sin que nadie asintiera.
     * Que un "sí, guárdalo" signifique de verdad asentimiento es cosa del CK;
     * aquí solo se exige que exista un turno posterior al que señalar. */
    if (strcmp(confirmacion_id, h->evidencia) == 0)
        return HERA_RECHAZO_SIN_CONFIRMACION;
    if (indice_dicho(confirmacion_id) <= indice_dicho(h->evidencia))
        return HERA_RECHAZO_SIN_CONFIRMACION;
#endif

    if (ensayo) return HERA_OK;

    char linea[160];
    snprintf(linea, sizeof(linea),
             "{\"r\":\"confirma\",\"id\":\"%s\",\"por\":\"%s\",\"ts\":%lld}",
             id, confirmacion_id, ahora());
    if (!anexar(linea)) return HERA_RECHAZO_INVALIDO;
    h->estado = HERA_CONFIRMADO;
    snprintf(h->confirmacion, sizeof(h->confirmacion), "%s", confirmacion_id);
    return HERA_OK;
}

hera_veredicto_t hera_store_confirmar(const char *id,
                                      const char *confirmacion_id) {
    bloquear(LOCK_EX);
    recargar(true);
    const hera_veredicto_t v = confirmar_impl(id, confirmacion_id, false);
    desbloquear();
    return v;
}

static hera_veredicto_t corregir_impl(const char *clave, const char *valor,
                                      const char *texto,
                                      const char *evidencia_id,
                                      const char *confirmacion_id,
                                      bool ensayo, char *out_id, size_t cap) {
    if (!evidencia_interna(confirmacion_id))
        return HERA_RECHAZO_SIN_CONFIRMACION;
    const hera_veredicto_t v = validar(clave, valor, evidencia_id);
    if (v != HERA_OK) return v;

    hera_hecho_t *viejo = vigente(clave);
    if (!viejo) return HERA_RECHAZO_DESCONOCIDO;
    if (ensayo) return HERA_OK;

#if HERA_SABOTAJE == 2
    /* Sabotaje: vuelve el bug de las dos escrituras. Si el proceso muere
     * entre ambas, al releer quedan dos confirmados contradiciéndose. */
    {
        char id[HERA_ID_MAX], viejo_id[HERA_ID_MAX];
        snprintf(viejo_id, sizeof(viejo_id), "%s", viejo->id);
        const hera_veredicto_t a = alta(clave, valor, texto, evidencia_id,
                                        confirmacion_id, true, "persona",
                                        NULL, id, sizeof(id));
        if (a != HERA_OK) return a;
        char l2[160];
        snprintf(l2, sizeof(l2),
                 "{\"r\":\"sustituye\",\"viejo\":\"%s\",\"nuevo\":\"%s\","
                 "\"ts\":%lld}", viejo_id, id, ahora());
        anexar(l2);
        hera_hecho_t *v2 = buscar_hecho(viejo_id);
        if (v2) { v2->estado = HERA_SUSTITUIDO;
                  snprintf(v2->sustituido_por, sizeof(v2->sustituido_por), "%s", id); }
        if (out_id && cap) snprintf(out_id, cap, "%s", id);
        return HERA_OK;
    }
#endif
    /* UN solo registro: crear y jubilar van juntos o no van. */
    return alta(clave, valor, texto, evidencia_id, confirmacion_id, true,
                "persona", viejo->id, out_id, cap);
}

hera_veredicto_t hera_store_corregir(const char *clave, const char *valor,
                                     const char *texto,
                                     const char *evidencia_id,
                                     const char *confirmacion_id,
                                     char *out_id, size_t cap) {
    bloquear(LOCK_EX);
    recargar(true);
    const hera_veredicto_t v =
        corregir_impl(clave, valor, texto, evidencia_id, confirmacion_id,
                      false, out_id, cap);
    desbloquear();
    return v;
}

/* ------------------------------------------------------------------------
 * Ensayo: mismo veredicto, cero escrituras.
 * ------------------------------------------------------------------------ */

hera_veredicto_t hera_store_ensayar_proponer(const char *clave,
                                             const char *valor,
                                             const char *evidencia_id) {
    bloquear(LOCK_SH);
    recargar(false);
    const hera_veredicto_t v = proponer_impl(clave, valor, NULL, evidencia_id, true, NULL, 0);
    desbloquear();
    return v;
}

hera_veredicto_t hera_store_ensayar_confirmar(const char *id,
                                              const char *confirmacion_id) {
    bloquear(LOCK_SH);
    recargar(false);
    const hera_veredicto_t v = confirmar_impl(id, confirmacion_id, true);
    desbloquear();
    return v;
}

hera_veredicto_t hera_store_ensayar_corregir(const char *clave,
                                             const char *valor,
                                             const char *evidencia_id,
                                             const char *confirmacion_id) {
    bloquear(LOCK_SH);
    recargar(false);
    const hera_veredicto_t v =
        corregir_impl(clave, valor, NULL, evidencia_id, confirmacion_id,
                      true, NULL, 0);
    desbloquear();
    return v;
}

/* ------------------------------------------------------------------------
 * Lectura
 * ------------------------------------------------------------------------ */

size_t hera_store_confirmados(hera_hecho_t *out, size_t cap) {
    size_t n = 0;
    bloquear(LOCK_SH);
    recargar(false);
    for (size_t i = 0; i < g_hechos_n && n < cap; i++) {
#if HERA_SABOTAJE == 3
        /* Sabotaje: los candidatos se cuelan entre los hechos vigentes, que
         * es justo lo que no debe entrar nunca al prompt. */
        if (g_hechos[i].estado == HERA_SUSTITUIDO) continue;
#else
        if (g_hechos[i].estado != HERA_CONFIRMADO) continue;
#endif
        out[n++] = g_hechos[i];
    }
    desbloquear();
    return n;
}

size_t hera_store_todos(hera_hecho_t *out, size_t cap) {
    size_t n = 0;
    bloquear(LOCK_SH);
    recargar(false);
    for (size_t i = 0; i < g_hechos_n && n < cap; i++) out[n++] = g_hechos[i];
    desbloquear();
    return n;
}

size_t hera_store_historial(const char *clave, hera_hecho_t *out, size_t cap) {
    size_t n = 0;
    if (!clave) return 0;
    bloquear(LOCK_SH);
    recargar(false);
    for (size_t i = 0; i < g_hechos_n && n < cap; i++)
        if (strcmp(g_hechos[i].clave, clave) == 0) out[n++] = g_hechos[i];
    desbloquear();
    return n;
}

/* ------------------------------------------------------------------------
 * Importación legacy — TODO EN CUARENTENA
 * ------------------------------------------------------------------------ */

static size_t importar_fichero(const char *nombre) {
    char dir[1024], ruta[1200];
    directorio(dir, sizeof(dir));
    snprintf(ruta, sizeof(ruta), "%s/%s", dir, nombre);
    FILE *f = fopen(ruta, "r");
    if (!f) return 0;

    size_t n = 0;
    char linea[HERA_TEXTO_MAX];
    while (fgets(linea, sizeof(linea), f)) {
        char *s = linea;
        while (*s == ' ' || *s == '\t') s++;
        if (s[0] != '-' || s[1] != ' ') continue;   /* solo viñetas */
        s += 2;
        size_t l = strlen(s);
        while (l && (s[l - 1] == '\n' || s[l - 1] == '\r' || s[l - 1] == ' '))
            s[--l] = '\0';
        if (!l) continue;

        /* La clave legacy es el propio texto: no había sujeto ni predicado, y
         * inventarle uno sería decidir por el pasado. Prefijo propio para que
         * no colisione con las claves nuevas ni pueda ser corregida como si
         * fuera una: primero hay que confirmarla. */
        char clave[HERA_CLAVE_MAX];
        snprintf(clave, sizeof(clave), "legacy/%.*s",
                 (int)(HERA_CLAVE_MAX - 10), s);
        if (es_duplicado(clave, s)) continue;

        /* CANDIDATO, siempre. `facts.md` tiene hechos falsos e identidades
         * inventadas: importarlo como autoridad mudaría la contaminación vieja
         * al almacén nuevo y dejaría la regla 1 en un adorno. */
#if HERA_SABOTAJE == 7
        /* Sabotaje: la memoria legacy envenenada entra como autoridad. */
        if (alta(clave, s, s, NULL, NULL, true, "legacy", NULL, NULL, 0)
                == HERA_OK) n++;
#else
        if (alta(clave, s, s, NULL, NULL, false, "legacy", NULL, NULL, 0)
                == HERA_OK) n++;
#endif
    }
    fclose(f);
    return n;
}

size_t hera_store_importar_legacy(void) {
    if (!g_abierto) return 0;
    bloquear(LOCK_EX);
    recargar(true);
    if (g_importado) { desbloquear(); return 0; }
    const size_t n = importar_fichero("facts.md") +
                     importar_fichero("candidates.md");
    char linea[128];
    snprintf(linea, sizeof(linea),
             "{\"r\":\"importado\",\"ts\":%lld,\"n\":%zu}", ahora(), n);
    anexar(linea);
    g_importado = true;
    desbloquear();
    return n;
}
