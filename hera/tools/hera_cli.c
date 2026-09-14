/*
 * hera — operar la memoria de un perfil desde la línea de órdenes.
 *
 * Existe porque en E3 NO HAY APLICADOR: la reflexión está desconectada a
 * propósito, así que la única forma de que un hecho nazca o se corrija es que
 * alguien lo pida explícitamente. Esto es ese "alguien" mientras tanto, y es
 * también lo que permite probar una corrección en caliente contra la ruta
 * tipada sin inventarse un camino de escritura que el plan no autoriza.
 *
 * Pasa por la MISMA API que usaría cualquier otro: no hay atajos aquí. Un
 * hecho escrito por esta CLI cumple las mismas reglas o no se escribe.
 *
 *   hera dijo   "<texto>"                        -> registra evidencia, da su id
 *   hera guarda <clave> <valor> <texto> <ev>     -> confirmado en un paso
 *   hera propon <clave> <valor> <texto> <ev>     -> candidato
 *   hera confirma <id> <conf>                    -> asciende un candidato
 *   hera corrige <clave> <valor> <texto> <ev> <conf>
 *   hera lista [--todo]                          -> vigentes, o todo con estado
 *   hera historial <clave>                       -> la cadena de correcciones
 *   hera perfil                                  -> lo que vería el prompt
 */

#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif
#include "hera_profile.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static int uso(void) {
    fprintf(stderr,
        "uso: hera <orden> [...]   (perfil por HELIOS_HOME)\n"
        "  dijo <texto>\n"
        "  guarda <clave> <valor> <texto> <evidencia>\n"
        "  propon <clave> <valor> <texto> <evidencia>\n"
        "  confirma <id> <confirmacion>\n"
        "  corrige <clave> <valor> <texto> <evidencia> <confirmacion>\n"
        "  lista [--todo] · historial <clave> · perfil\n");
    return 2;
}

static int veredicto(hera_veredicto_t v, const char *id) {
    if (v == HERA_OK) { printf("ok%s%s\n", id && *id ? " " : "", id ? id : ""); return 0; }
    fprintf(stderr, "rechazado: %s\n", hera_veredicto_nombre(v));
    return 1;
}

/* Una cadena JSON valida: comillas, barras y control escapados. Los bytes UTF-8
 * pasan tal cual, que ya son validos dentro de una cadena JSON. */
static void json_cadena(const char *s) {
    putchar('"');
    for (const unsigned char *p = (const unsigned char *)(s ? s : ""); *p; p++) {
        switch (*p) {
            case '"':  fputs("\\\"", stdout); break;
            case '\\': fputs("\\\\", stdout); break;
            case '\n': fputs("\\n", stdout); break;
            case '\r': fputs("\\r", stdout); break;
            case '\t': fputs("\\t", stdout); break;
            case '\b': fputs("\\b", stdout); break;
            case '\f': fputs("\\f", stdout); break;
            default:
                if (*p < 0x20) printf("\\u%04x", *p);
                else putchar(*p);
        }
    }
    putchar('"');
}


int main(int argc, char **argv) {
    if (argc < 2) return uso();
    if (!hera_store_abrir()) {
        fprintf(stderr, "no pude abrir la memoria del perfil\n");
        return 1;
    }
    /* El agente solo recupera confirmados: no importa ficheros legacy al leer. */
    if (strcmp(argv[1], "perfil-agente")) hera_store_importar_legacy();

    const char *o = argv[1];
    char id[HERA_ID_MAX] = "";

    if (!strcmp(o, "dijo") && argc == 3) {
        if (!hera_store_dijo(argv[2], id, sizeof(id))) return 1;
        printf("%s\n", id);
        return 0;
    }
    if (!strcmp(o, "guarda") && argc == 6)
        return veredicto(hera_store_registrar(argv[2], argv[3], argv[4],
                                              argv[5], argv[5], id, sizeof(id)), id);
    if (!strcmp(o, "propon") && argc == 6)
        return veredicto(hera_store_proponer(argv[2], argv[3], argv[4],
                                             argv[5], id, sizeof(id)), id);
    if (!strcmp(o, "confirma") && argc == 4)
        return veredicto(hera_store_confirmar(argv[2], argv[3]), NULL);
    if (!strcmp(o, "corrige") && argc == 7)
        return veredicto(hera_store_corregir(argv[2], argv[3], argv[4],
                                             argv[5], argv[6], id, sizeof(id)), id);

    if (!strcmp(o, "lista")) {
        const bool todo = (argc > 2 && !strcmp(argv[2], "--todo"));
        /* --json: un objeto con los hechos y si la lectura quedo incompleta.
         * El formato alineado usa %-28s, que fija un ancho MINIMO y no maximo: una
         * clave larga desborda la columna y quien lea por posiciones ya no puede
         * saber donde acaba. Con cadenas escapadas no hay nada que desbordar, y
         * `truncated` evita que "no aparecio" se lea como "no existe". */
        const bool como_json = (argc > 2 && !strcmp(argv[2], "--json"));
        enum { CUPO = 256 };
        hera_hecho_t hs[CUPO];
        const size_t n = todo ? hera_store_todos(hs, CUPO)
                              : hera_store_confirmados(hs, CUPO);
        if (como_json) {
            fputs("{\"facts\":[", stdout);
            for (size_t i = 0; i < n; i++) {
                if (i) putchar(',');
                fputs("{\"id\":", stdout);      json_cadena(hs[i].id);
                fputs(",\"state\":", stdout);   json_cadena(hera_estado_nombre(hs[i].estado));
                fputs(",\"key\":", stdout);     json_cadena(hs[i].clave);
                fputs(",\"value\":", stdout);   json_cadena(hs[i].valor);
                fputs(",\"replaced_by\":", stdout); json_cadena(hs[i].sustituido_por);
                fputs(",\"evidence\":", stdout); json_cadena(hs[i].evidencia);
                putchar('}');
            }
            /* n == CUPO no demuestra que sobren, pero tampoco lo descarta: se
             * declara incompleta para que nadie concluya una ausencia. */
            printf("],\"count\":%zu,\"truncated\":%s}\n", n,
                   n >= (size_t)CUPO ? "true" : "false");
            return 0;
        }
        for (size_t i = 0; i < n; i++) {
            printf("%-5s %-11s %-28s %s", hs[i].id,
                   hera_estado_nombre(hs[i].estado), hs[i].clave, hs[i].valor);
            if (hs[i].sustituido_por[0]) printf("  -> %s", hs[i].sustituido_por);
            if (hs[i].evidencia[0]) printf("   [%s]", hs[i].evidencia);
            else printf("   [sin cita: %s]", hs[i].origen);
            putchar('\n');
        }
        if (!n) printf("(sin nada que enseñar)\n");
        return 0;
    }
    if (!strcmp(o, "historial") && argc == 3) {
        hera_hecho_t hs[64];
        const size_t n = hera_store_historial(argv[2], hs, 64);
        for (size_t i = 0; i < n; i++) {
            printf("%-5s %-11s %s\n", hs[i].id,
                   hera_estado_nombre(hs[i].estado), hs[i].valor);
            const char *ev = hera_store_evidencia(hs[i].evidencia);
            if (ev) printf("        porque dijo: \"%s\"\n", ev);
        }
        if (!n) printf("(nada bajo esa clave)\n");
        return 0;
    }
    if (!strcmp(o, "perfil") || !strcmp(o, "perfil-agente")) {
        char buf[8192];
        const size_t n = hera_recuperar(buf, sizeof(buf), 3000);
        if (!n) printf("(perfil vacío: nada confirmado todavía)\n");
        else fwrite(buf, 1, n, stdout);
        return 0;
    }
    return uso();
}
