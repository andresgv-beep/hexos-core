/*
 * HERA — almacén de memoria (E3)
 *
 * Ver hera_store.h para las tres reglas. Aquí solo el cómo.
 *
 * El diario es JSONL de solo añadir. Cada línea es un registro:
 *
 *   {"r":"dijo","id":"u1","ts":...,"texto":"mi perro se llama Byteazul"}
 *   {"r":"hecho","id":"f1","ts":...,"clave":"perro/nombre","valor":"Byteazul",
 *    "texto":"Su perro se llama Byteazul","estado":"confirmado",
 *    "evidencia":"u1","origen":"persona"}
 *   {"r":"confirma","id":"f1","ts":...}
 *   {"r":"sustituye","viejo":"f1","nuevo":"f2","ts":...}
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
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <time.h>

#define HECHOS_MAX     4096
#define DICHOS_MAX     4096

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

const char *hera_veredicto_nombre(hera_veredicto_t v) {
    switch (v) {
        case HERA_OK:                     return "ok";
        case HERA_RECHAZO_SIN_EVIDENCIA:  return "sin_evidencia";
        case HERA_RECHAZO_NO_LITERAL:     return "no_literal";
        case HERA_RECHAZO_DUPLICADO:      return "duplicado";
        case HERA_RECHAZO_INVALIDO:       return "invalido";
        case HERA_RECHAZO_DESCONOCIDO:    return "desconocido";
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
 * bytes por la mitad. "Bilbao" y "bilbao" tienen que casar; "Bilbaó" y
 * "Bilbao" no, y eso es correcto — un acento distinto es otra palabra hasta
 * que alguien demuestre lo contrario.
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

/* ¿Aparecen TODAS las palabras significativas de `valor` dentro de `texto`?
 * Significativa = 3 bytes o más; las de una o dos letras ("de", "la") no
 * aportan y exigirlas rechazaría hechos legítimos. Palabra completa, no
 * subcadena: si no, "Ana" colaría dentro de "manzana". */
static bool valor_esta_en(const char *valor, const char *texto) {
#if HERA_SABOTAJE == 1
    /* Sabotaje: la comprobación de literalidad siempre dice que sí. Sirve
     * para verificar que la batería detecta un almacén roto. */
    (void)valor; (void)texto; return true;
#endif
    char nv[HERA_VALOR_MAX * 2], nt[HERA_UTTER_MAX * 2];
    normalizar(valor, nv, sizeof(nv));
    normalizar(texto, nt, sizeof(nt));

    bool alguna = false;
    char copia[HERA_VALOR_MAX * 2];
    snprintf(copia, sizeof(copia), "%s", nv);
    for (char *tok = strtok(copia, " "); tok; tok = strtok(NULL, " ")) {
        const size_t l = strlen(tok);
        if (l < 3) continue;
        alguna = true;
        bool visto = false;
        for (const char *p = strstr(nt, tok); p; p = strstr(p + 1, tok)) {
            const bool ini = (p == nt) || p[-1] == ' ';
            const bool fin = (p[l] == '\0') || p[l] == ' ';
            if (ini && fin) { visto = true; break; }
        }
        if (!visto) return false;
    }
    /* Un valor sin ninguna palabra significativa ("no", "42") no se puede
     * verificar de esta forma: se exige que aparezca entero como subcadena. */
    if (!alguna) return strstr(nt, nv) != NULL;
    return true;
}

/* Duplicado por contención de palabras, el criterio que ya usaba la legacy:
 * pilla copias, trozos y versiones ampliadas del mismo hecho. */
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
 * JSON mínimo: escribir y leer los pocos campos del diario.
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

/* Reloj fijable para que las pruebas puedan comparar diarios byte a byte.
 * Sin la variable, la hora de verdad. */
static long long ahora(void) {
    const char *fijo = getenv("HERA_TS_FIJO");
    if (fijo && *fijo) return atoll(fijo);
    return (long long)time(NULL);
}

static bool anexar(const char *linea) {
    FILE *f = fopen(g_ruta, "a");
    if (!f) return false;
    fputs(linea, f);
    fputc('\n', f);
    fclose(f);
    return true;
}

static hera_hecho_t *buscar_hecho(const char *id) {
    for (size_t i = 0; i < g_hechos_n; i++)
        if (strcmp(g_hechos[i].id, id) == 0) return &g_hechos[i];
    return NULL;
}

/* Hecho vigente de una clave: confirmado y sin sustituir. */
static hera_hecho_t *vigente(const char *clave) {
    for (size_t i = g_hechos_n; i > 0; i--) {
        hera_hecho_t *h = &g_hechos[i - 1];
        if (h->estado == HERA_CONFIRMADO && strcmp(h->clave, clave) == 0)
            return h;
    }
    return NULL;
}

const char *hera_store_evidencia(const char *id) {
    if (!id || !*id) return NULL;
    for (size_t i = 0; i < g_dichos_n; i++)
        if (strcmp(g_dichos[i].id, id) == 0) return g_dichos[i].texto;
    return NULL;
}

const char *hera_store_ruta(void) { return g_ruta; }

/* ------------------------------------------------------------------------
 * Apertura: reconstruir el estado leyendo el diario entero.
 * ------------------------------------------------------------------------ */

static void aplicar(const char *linea) {
    char r[32];
    if (!leer_campo(linea, "r", r, sizeof(r))) return;

    if (strcmp(r, "dijo") == 0) {
        if (g_dichos_n >= DICHOS_MAX) return;
        dicho_t *d = &g_dichos[g_dichos_n];
        if (!leer_campo(linea, "id", d->id, sizeof(d->id))) return;
        leer_campo(linea, "texto", d->texto, sizeof(d->texto));
        unsigned n = 0;
        if (sscanf(d->id, "u%u", &n) == 1 && n > g_seq_u) g_seq_u = n;
        g_dichos_n++;
        return;
    }
    if (strcmp(r, "hecho") == 0) {
        if (g_hechos_n >= HECHOS_MAX) return;
        hera_hecho_t *h = &g_hechos[g_hechos_n];
        memset(h, 0, sizeof(*h));
        if (!leer_campo(linea, "id", h->id, sizeof(h->id))) return;
        leer_campo(linea, "clave", h->clave, sizeof(h->clave));
        leer_campo(linea, "valor", h->valor, sizeof(h->valor));
        leer_campo(linea, "texto", h->texto, sizeof(h->texto));
        leer_campo(linea, "evidencia", h->evidencia, sizeof(h->evidencia));
        leer_campo(linea, "origen", h->origen, sizeof(h->origen));
        char est[24] = "candidato";
        leer_campo(linea, "estado", est, sizeof(est));
        h->estado = (strcmp(est, "confirmado") == 0) ? HERA_CONFIRMADO
                                                     : HERA_CANDIDATO;
        const char *ts = strstr(linea, "\"ts\":");
        h->ts = ts ? atoll(ts + 5) : 0;
        unsigned n = 0;
        if (sscanf(h->id, "f%u", &n) == 1 && n > g_seq_f) g_seq_f = n;
        g_hechos_n++;
        return;
    }
    if (strcmp(r, "confirma") == 0) {
        char id[HERA_ID_MAX];
        if (!leer_campo(linea, "id", id, sizeof(id))) return;
        hera_hecho_t *h = buscar_hecho(id);
        if (h && h->estado == HERA_CANDIDATO) h->estado = HERA_CONFIRMADO;
        return;
    }
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

bool hera_store_abrir(void) {
    char dir[1024];
    directorio(dir, sizeof(dir));
    snprintf(g_ruta, sizeof(g_ruta), "%s/hera.jsonl", dir);

    g_hechos_n = g_dichos_n = 0;
    g_seq_u = g_seq_f = 0;
    g_importado = false;

    FILE *f = fopen(g_ruta, "r");
    if (f) {
        char *linea = malloc(HERA_UTTER_MAX * 2);
        if (linea) {
            while (fgets(linea, (int)(HERA_UTTER_MAX * 2), f)) aplicar(linea);
            free(linea);
        }
        fclose(f);
    } else {
        /* Crear el fichero ya, para fallar aquí si el perfil no es escribible
         * y no a mitad del primer turno. */
        f = fopen(g_ruta, "a");
        if (!f) return false;
        fclose(f);
    }
    g_abierto = true;
    return true;
}

void hera_store_cerrar(void) {
    g_abierto = false;
    g_hechos_n = g_dichos_n = 0;
    g_ruta[0] = '\0';
}

/* ------------------------------------------------------------------------
 * Escritura
 * ------------------------------------------------------------------------ */

bool hera_store_dijo(const char *texto, char *out_id, size_t cap) {
    if (!g_abierto || !texto || !*texto) return false;
    if (g_dichos_n >= DICHOS_MAX) return false;

    char id[HERA_ID_MAX];
    snprintf(id, sizeof(id), "u%u", ++g_seq_u);

    char e[HERA_UTTER_MAX * 2];
    esc(texto, e, sizeof(e));
    char linea[HERA_UTTER_MAX * 2 + 128];
    snprintf(linea, sizeof(linea),
             "{\"r\":\"dijo\",\"id\":\"%s\",\"ts\":%lld,\"texto\":\"%s\"}",
             id, ahora(), e);
    if (!anexar(linea)) return false;

    dicho_t *d = &g_dichos[g_dichos_n++];
    snprintf(d->id, sizeof(d->id), "%s", id);
    snprintf(d->texto, sizeof(d->texto), "%s", texto);
    if (out_id && cap) snprintf(out_id, cap, "%s", id);
    return true;
}

/* Alta de un hecho ya validado. `sin_evidencia` solo lo usa la importación
 * legacy; el camino normal nunca pasa por aquí sin cita. */
static hera_veredicto_t alta(const char *clave, const char *valor,
                             const char *texto, const char *evidencia_id,
                             bool confirmado, const char *origen,
                             char *out_id, size_t cap) {
    if (g_hechos_n >= HECHOS_MAX) return HERA_RECHAZO_INVALIDO;

    char id[HERA_ID_MAX];
    snprintf(id, sizeof(id), "f%u", ++g_seq_f);

    char ec[HERA_CLAVE_MAX * 2], ev[HERA_VALOR_MAX * 2], et[HERA_TEXTO_MAX * 2];
    esc(clave, ec, sizeof(ec));
    esc(valor, ev, sizeof(ev));
    esc(texto && *texto ? texto : valor, et, sizeof(et));

    char linea[HERA_TEXTO_MAX * 4];
    snprintf(linea, sizeof(linea),
             "{\"r\":\"hecho\",\"id\":\"%s\",\"ts\":%lld,\"clave\":\"%s\","
             "\"valor\":\"%s\",\"texto\":\"%s\",\"estado\":\"%s\","
             "\"evidencia\":\"%s\",\"origen\":\"%s\"}",
             id, ahora(), ec, ev, et,
             confirmado ? "confirmado" : "candidato",
             evidencia_id ? evidencia_id : "", origen);
    if (!anexar(linea)) return HERA_RECHAZO_INVALIDO;

    hera_hecho_t *h = &g_hechos[g_hechos_n++];
    memset(h, 0, sizeof(*h));
    snprintf(h->id, sizeof(h->id), "%s", id);
    snprintf(h->clave, sizeof(h->clave), "%s", clave);
    snprintf(h->valor, sizeof(h->valor), "%s", valor);
    snprintf(h->texto, sizeof(h->texto), "%s", texto && *texto ? texto : valor);
    snprintf(h->evidencia, sizeof(h->evidencia), "%s",
             evidencia_id ? evidencia_id : "");
    snprintf(h->origen, sizeof(h->origen), "%s", origen);
    h->estado = confirmado ? HERA_CONFIRMADO : HERA_CANDIDATO;
    h->ts = ahora();
    if (out_id && cap) snprintf(out_id, cap, "%s", id);
    return HERA_OK;
}

/* La puerta única. Todo lo que entre por aquí trae cita comprobada. */
static hera_veredicto_t validar(const char *clave, const char *valor,
                                const char *evidencia_id) {
    if (!g_abierto) return HERA_RECHAZO_INVALIDO;
    if (!clave || !*clave || !valor || !*valor) return HERA_RECHAZO_INVALIDO;
    if (strlen(clave) >= HERA_CLAVE_MAX || strlen(valor) >= HERA_VALOR_MAX)
        return HERA_RECHAZO_INVALIDO;

    const char *dicho = hera_store_evidencia(evidencia_id);
    if (!dicho) return HERA_RECHAZO_SIN_EVIDENCIA;
    if (!valor_esta_en(valor, dicho)) return HERA_RECHAZO_NO_LITERAL;
    return HERA_OK;
}

hera_veredicto_t hera_store_proponer(const char *clave, const char *valor,
                                     const char *texto,
                                     const char *evidencia_id,
                                     bool confirmado,
                                     char *out_id, size_t cap) {
    const hera_veredicto_t v = validar(clave, valor, evidencia_id);
    if (v != HERA_OK) return v;
    if (es_duplicado(clave, valor)) return HERA_RECHAZO_DUPLICADO;
    return alta(clave, valor, texto, evidencia_id, confirmado,
                confirmado ? "persona" : "modelo", out_id, cap);
}

hera_veredicto_t hera_store_confirmar(const char *id) {
    if (!g_abierto || !id || !*id) return HERA_RECHAZO_INVALIDO;
    hera_hecho_t *h = buscar_hecho(id);
    if (!h) return HERA_RECHAZO_DESCONOCIDO;
    if (h->estado == HERA_SUSTITUIDO) return HERA_RECHAZO_DESCONOCIDO;
    if (h->estado == HERA_CONFIRMADO) return HERA_OK;

    char linea[128];
    snprintf(linea, sizeof(linea),
             "{\"r\":\"confirma\",\"id\":\"%s\",\"ts\":%lld}", id, ahora());
    if (!anexar(linea)) return HERA_RECHAZO_INVALIDO;
    h->estado = HERA_CONFIRMADO;
    return HERA_OK;
}

hera_veredicto_t hera_store_corregir(const char *clave, const char *valor,
                                     const char *texto,
                                     const char *evidencia_id,
                                     char *out_id, size_t cap) {
    const hera_veredicto_t v = validar(clave, valor, evidencia_id);
    if (v != HERA_OK) return v;

    hera_hecho_t *viejo = vigente(clave);
    if (!viejo) return HERA_RECHAZO_DESCONOCIDO;

    char id[HERA_ID_MAX];
    const hera_veredicto_t a = alta(clave, valor, texto, evidencia_id, true,
                                    "persona", id, sizeof(id));
    if (a != HERA_OK) return a;

#if HERA_SABOTAJE == 2
    /* Sabotaje: corregir se limita a añadir, como hacía la legacy. El hecho
     * viejo sigue vigente y la memoria se contradice en silencio. */
    if (out_id && cap) snprintf(out_id, cap, "%s", id);
    return HERA_OK;
#endif
    char linea[160];
    snprintf(linea, sizeof(linea),
             "{\"r\":\"sustituye\",\"viejo\":\"%s\",\"nuevo\":\"%s\",\"ts\":%lld}",
             viejo->id, id, ahora());
    if (!anexar(linea)) return HERA_RECHAZO_INVALIDO;

    /* `viejo` puede haberse invalidado si alta() movió el array; se rebusca. */
    hera_hecho_t *v2 = buscar_hecho(viejo->id);
    if (v2) {
        v2->estado = HERA_SUSTITUIDO;
        snprintf(v2->sustituido_por, sizeof(v2->sustituido_por), "%s", id);
    }
    if (out_id && cap) snprintf(out_id, cap, "%s", id);
    return HERA_OK;
}

/* ------------------------------------------------------------------------
 * Lectura
 * ------------------------------------------------------------------------ */

size_t hera_store_confirmados(hera_hecho_t *out, size_t cap) {
    size_t n = 0;
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
    return n;
}

size_t hera_store_todos(hera_hecho_t *out, size_t cap) {
    size_t n = 0;
    for (size_t i = 0; i < g_hechos_n && n < cap; i++) out[n++] = g_hechos[i];
    return n;
}

size_t hera_store_historial(const char *clave, hera_hecho_t *out, size_t cap) {
    size_t n = 0;
    if (!clave) return 0;
    for (size_t i = 0; i < g_hechos_n && n < cap; i++)
        if (strcmp(g_hechos[i].clave, clave) == 0) out[n++] = g_hechos[i];
    return n;
}

/* ------------------------------------------------------------------------
 * Importación legacy
 * ------------------------------------------------------------------------ */

static size_t importar_fichero(const char *nombre, bool confirmado) {
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

        /* La clave legacy es el propio texto: no había sujeto ni predicado,
         * así que no se puede inventar uno sin decidir por el pasado. Se
         * marcan con prefijo para que no colisionen con las claves nuevas. */
        char clave[HERA_CLAVE_MAX];
        snprintf(clave, sizeof(clave), "legacy/%.*s",
                 (int)(HERA_CLAVE_MAX - 10), s);
        if (es_duplicado(clave, s)) continue;
        if (alta(clave, s, s, NULL, confirmado, "legacy", NULL, 0) == HERA_OK)
            n++;
    }
    fclose(f);
    return n;
}

size_t hera_store_importar_legacy(void) {
    if (!g_abierto || g_importado) return 0;
    const size_t n = importar_fichero("facts.md", true) +
                     importar_fichero("candidates.md", false);
    char linea[128];
    snprintf(linea, sizeof(linea),
             "{\"r\":\"importado\",\"ts\":%lld,\"n\":%zu}", ahora(), n);
    anexar(linea);
    g_importado = true;
    return n;
}
