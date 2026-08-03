/*
 * Batería de la barrera de E3.
 *
 * Cada prueba corre en un perfil recién creado (HELIOS_HOME propio) para que
 * ninguna herede el estado de la anterior — que es, además, uno de los puntos
 * que hay que demostrar.
 *
 * Con `--sabotaje N` el binario se rompe a propósito de la forma N. Sirve
 * para comprobar que la batería DETECTA el fallo: una prueba que pasa contra
 * un almacén saboteado no está probando nada. Los sabotajes son:
 *   1  la comprobación de evidencia siempre dice que sí
 *   2  corregir añade en vez de sustituir
 *   3  los candidatos se cuelan entre los confirmados
 */

#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif
#include "hera_store.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

static int g_fallos, g_pruebas;
static char g_base[512];

static void ok(bool cond, const char *nombre, const char *detalle) {
    g_pruebas++;
    if (cond) {
        printf("  \033[32m✓\033[0m %s\n", nombre);
    } else {
        g_fallos++;
        printf("  \033[31m✗ %s\033[0m — %s\n", nombre, detalle);
    }
}

/* Perfil limpio y aislado por prueba. */
static void perfil(const char *nombre) {
    char dir[700];
    snprintf(dir, sizeof(dir), "%s/%s", g_base, nombre);
    char cmd[800];
    snprintf(cmd, sizeof(cmd), "rm -rf '%s'", dir);
    if (system(cmd) != 0) { /* no existía: perfecto */ }
    mkdir(dir, 0755);
    setenv("HELIOS_HOME", dir, 1);
    setenv("HERA_TS_FIJO", "1700000000", 1);
    hera_store_abrir();
}

/* ---------------------------------------------------------------------- */

/* "Ana vive en Bilbao": el hecho estrella que tiene que ser imposible. */
static void prueba_sin_evidencia(void) {
    printf("\n[1] ningún recuerdo nace sin evidencia\n");
    perfil("p1");

    hera_veredicto_t v = hera_store_proponer("ana/ciudad", "Bilbao",
        "Ana vive en Bilbao", NULL, true, NULL, 0);
    ok(v == HERA_RECHAZO_SIN_EVIDENCIA,
       "sin citar nada dicho → rechazado",
       hera_veredicto_nombre(v));

    v = hera_store_proponer("ana/ciudad", "Bilbao", "Ana vive en Bilbao",
                            "u99", true, NULL, 0);
    ok(v == HERA_RECHAZO_SIN_EVIDENCIA,
       "citando una evidencia inventada → rechazado",
       hera_veredicto_nombre(v));

    /* La persona habla de Ana, pero nunca de Bilbao. */
    char u[HERA_ID_MAX];
    hera_store_dijo("Ana es mi hermana y trabaja de enfermera", u, sizeof(u));
    v = hera_store_proponer("ana/ciudad", "Bilbao", "Ana vive en Bilbao",
                            u, true, NULL, 0);
    ok(v == HERA_RECHAZO_NO_LITERAL,
       "citando algo real que NO dice Bilbao → rechazado",
       hera_veredicto_nombre(v));

    /* Lo que sí dijo, se guarda. */
    v = hera_store_proponer("ana/oficio", "enfermera",
                            "Su hermana Ana es enfermera", u, true, NULL, 0);
    ok(v == HERA_OK, "el dato que sí está en sus palabras → aceptado",
       hera_veredicto_nombre(v));

    hera_hecho_t hs[16];
    size_t n = hera_store_confirmados(hs, 16);
    ok(n == 1 && strcmp(hs[0].valor, "enfermera") == 0,
       "solo queda el hecho con evidencia", "hay más de uno o es otro");
}

/* Palabra completa, no subcadena: "Ana" no vale dentro de "manzana". */
static void prueba_frontera_de_palabra(void) {
    printf("\n[2] la evidencia se mide por palabra, no por subcadena\n");
    perfil("p2");

    char u[HERA_ID_MAX];
    hera_store_dijo("me comí una manzana en el parque", u, sizeof(u));
    hera_veredicto_t v = hera_store_proponer("persona/nombre", "Ana",
                                             "Se llama Ana", u, true, NULL, 0);
    ok(v == HERA_RECHAZO_NO_LITERAL,
       "\"Ana\" escondida dentro de \"manzana\" → rechazado",
       hera_veredicto_nombre(v));

    hera_store_dijo("mi hermana Ana viene el jueves", u, sizeof(u));
    v = hera_store_proponer("persona/nombre", "Ana", "Se llama Ana", u,
                            true, NULL, 0);
    ok(v == HERA_OK, "\"Ana\" como palabra suelta → aceptado",
       hera_veredicto_nombre(v));
}

/* Una corrección sustituye y se puede auditar. */
static void prueba_correccion(void) {
    printf("\n[3] corregir sustituye, y la transición se audita\n");
    perfil("p3");

    char u1[HERA_ID_MAX], u2[HERA_ID_MAX], f1[HERA_ID_MAX], f2[HERA_ID_MAX];
    hera_store_dijo("mi perro se llama Byteazul", u1, sizeof(u1));
    hera_store_proponer("perro/nombre", "Byteazul", "Su perro se llama Byteazul",
                        u1, true, f1, sizeof(f1));

    hera_store_dijo("me equivoqué, el perro se llama Rufo", u2, sizeof(u2));
    hera_veredicto_t v = hera_store_corregir("perro/nombre", "Rufo",
        "Su perro se llama Rufo", u2, f2, sizeof(f2));
    ok(v == HERA_OK, "la corrección entra", hera_veredicto_nombre(v));

    hera_hecho_t hs[16];
    size_t n = hera_store_confirmados(hs, 16);
    ok(n == 1, "queda UN hecho vigente, no dos que se contradicen",
       "el viejo sigue vivo");
    ok(n == 1 && strcmp(hs[0].valor, "Rufo") == 0,
       "el vigente es el corregido", "sigue mandando el viejo");

    n = hera_store_historial("perro/nombre", hs, 16);
    ok(n == 2, "el historial conserva los dos", "se perdió el viejo");
    bool cadena = false;
    for (size_t i = 0; i < n; i++)
        if (strcmp(hs[i].id, f1) == 0 &&
            hs[i].estado == HERA_SUSTITUIDO &&
            strcmp(hs[i].sustituido_por, f2) == 0) cadena = true;
    ok(cadena, "el viejo queda marcado y apunta al nuevo",
       "no hay puntero de sustitución");

    /* La auditoría llega hasta las palabras exactas que causaron el cambio. */
    const char *ev = hera_store_evidencia(u2);
    ok(ev && strstr(ev, "Rufo") != NULL,
       "la evidencia del cambio es recuperable", "no se puede citar el porqué");

    /* Corregir algo que nunca se supo no es corregir. */
    v = hera_store_corregir("gato/nombre", "Rufo", "x", u2, NULL, 0);
    ok(v == HERA_RECHAZO_DESCONOCIDO,
       "corregir lo que no existe → rechazado", hera_veredicto_nombre(v));
}

/* Los candidatos no son hechos. */
static void prueba_candidatos(void) {
    printf("\n[4] los candidatos no entran al prompt\n");
    perfil("p4");

    char u[HERA_ID_MAX], f[HERA_ID_MAX];
    hera_store_dijo("creo que me mudo a Girona en otoño", u, sizeof(u));
    hera_store_proponer("persona/ciudad", "Girona", "Se muda a Girona", u,
                        false, f, sizeof(f));

    hera_hecho_t hs[16];
    ok(hera_store_confirmados(hs, 16) == 0,
       "un candidato no aparece entre los confirmados", "se coló");
    ok(hera_store_todos(hs, 16) == 1,
       "pero sigue guardado para poder confirmarlo luego", "se perdió");

    ok(hera_store_confirmar(f) == HERA_OK, "la persona lo confirma", "falló");
    ok(hera_store_confirmados(hs, 16) == 1,
       "y entonces sí es un hecho", "no ascendió");
}

/* Reiniciar conserva exactamente el estado confirmado. */
static void prueba_reinicio(void) {
    printf("\n[5] reiniciar conserva exactamente el estado confirmado\n");
    perfil("p5");

    char u[HERA_ID_MAX], c[HERA_ID_MAX];
    hera_store_dijo("mi perro se llama Byteazul y vivo en Sevilla", u, sizeof(u));
    hera_store_proponer("perro/nombre", "Byteazul", "Su perro es Byteazul", u,
                        true, NULL, 0);
    hera_store_proponer("persona/ciudad", "Sevilla", "Vive en Sevilla", u,
                        false, c, sizeof(c));
    hera_store_dijo("perdona, el perro es Rufo", u, sizeof(u));
    hera_store_corregir("perro/nombre", "Rufo", "Su perro es Rufo", u, NULL, 0);

    hera_hecho_t antes[16];
    const size_t na = hera_store_confirmados(antes, 16);

    hera_store_cerrar();
    ok(hera_store_abrir(), "el diario se relee", "no abre");

    hera_hecho_t desp[16];
    const size_t nd = hera_store_confirmados(desp, 16);
    ok(na == nd, "mismo número de hechos vigentes", "cambió la cuenta");
    bool iguales = (na == nd);
    for (size_t i = 0; i < na && iguales; i++)
        iguales = strcmp(antes[i].id, desp[i].id) == 0 &&
                  strcmp(antes[i].valor, desp[i].valor) == 0 &&
                  antes[i].estado == desp[i].estado;
    ok(iguales, "y son exactamente los mismos", "algo cambió al releer");

    bool candidato_sigue_fuera = true;
    for (size_t i = 0; i < nd; i++)
        if (strcmp(desp[i].id, c) == 0) candidato_sigue_fuera = false;
    ok(candidato_sigue_fuera,
       "el candidato sigue sin ser un hecho tras reiniciar", "ascendió solo");

    bool sustituido_fuera = true;
    for (size_t i = 0; i < nd; i++)
        if (strcmp(desp[i].valor, "Byteazul") == 0) sustituido_fuera = false;
    ok(sustituido_fuera, "el hecho corregido no vuelve de entre los muertos",
       "el sustituido resucitó");
}

/* Un perfil vacío no recibe datos de otro. */
static void prueba_aislamiento(void) {
    printf("\n[6] un perfil vacío no hereda nada de otro\n");

    perfil("p6a");
    char u[HERA_ID_MAX];
    hera_store_dijo("mi perro se llama Byteazul", u, sizeof(u));
    hera_store_proponer("perro/nombre", "Byteazul", "Su perro es Byteazul", u,
                        true, NULL, 0);
    hera_hecho_t hs[16];
    ok(hera_store_confirmados(hs, 16) == 1, "el perfil A sabe su hecho", "no");

    perfil("p6b");
    ok(hera_store_confirmados(hs, 16) == 0,
       "el perfil B arranca sin hechos", "heredó memoria ajena");
    ok(hera_store_evidencia("u1") == NULL,
       "y no puede citar evidencias del otro perfil",
       "las evidencias cruzan perfiles");

    /* Ni siquiera reutilizando el mismo id: sin evidencia local, no hay hecho. */
    hera_veredicto_t v = hera_store_proponer("perro/nombre", "Byteazul",
        "Su perro es Byteazul", "u1", true, NULL, 0);
    ok(v == HERA_RECHAZO_SIN_EVIDENCIA,
       "reusar el id del otro perfil no cuela", hera_veredicto_nombre(v));
}

/* Compatibilidad de lectura con el almacén legacy. */
static void prueba_legacy(void) {
    printf("\n[7] compatibilidad de lectura con facts.md / candidates.md\n");
    perfil("p7");

    char dir[700], ruta[900];
    snprintf(dir, sizeof(dir), "%s/p7", g_base);
    snprintf(ruta, sizeof(ruta), "%s/facts.md", dir);
    FILE *f = fopen(ruta, "w");
    fputs("- Se llama Andrés y construye un motor de inferencia.\n"
          "- Su perro se llama Byteazul.\n", f);
    fclose(f);
    snprintf(ruta, sizeof(ruta), "%s/candidates.md", dir);
    f = fopen(ruta, "w");
    fputs("- Puede que esté escribiendo un libro.\n", f);
    fclose(f);

    hera_store_abrir();
    const size_t n = hera_store_importar_legacy();
    ok(n == 3, "importa los tres", "cuenta distinta");

    hera_hecho_t hs[16];
    ok(hera_store_confirmados(hs, 16) == 2,
       "los de facts.md son hechos; el candidato no", "reparto incorrecto");

    size_t legacy_sin_cita = 0;
    const size_t t = hera_store_todos(hs, 16);
    for (size_t i = 0; i < t; i++)
        if (strcmp(hs[i].origen, "legacy") == 0 && hs[i].evidencia[0] == '\0')
            legacy_sin_cita++;
    ok(legacy_sin_cita == 3,
       "quedan marcados como legacy y sin cita, visibles en la auditoría",
       "no se distinguen de los nuevos");

    ok(hera_store_importar_legacy() == 0,
       "importar dos veces no duplica", "duplicó");
    hera_store_cerrar();
    hera_store_abrir();
    ok(hera_store_importar_legacy() == 0,
       "ni siquiera tras reiniciar", "duplicó tras reiniciar");
}

/* ---------------------------------------------------------------------- */

int main(int argc, char **argv) {
    int sabotaje = 0;
    for (int i = 1; i < argc; i++)
        if (!strcmp(argv[i], "--sabotaje") && i + 1 < argc)
            sabotaje = atoi(argv[++i]);

    const char *tmp = getenv("TMPDIR");
    snprintf(g_base, sizeof(g_base), "%s/hera_e3_pruebas",
             tmp && *tmp ? tmp : "/tmp");
    mkdir(g_base, 0755);

    if (sabotaje) printf("\n\033[33mSABOTAJE %d activo — "
                         "la batería DEBE fallar\033[0m\n", sabotaje);
    printf("almacén bajo prueba: perfiles en %s\n", g_base);

    prueba_sin_evidencia();
    prueba_frontera_de_palabra();
    prueba_correccion();
    prueba_candidatos();
    prueba_reinicio();
    prueba_aislamiento();
    prueba_legacy();

    printf("\n%d pruebas · %d fallos\n", g_pruebas, g_fallos);
    if (sabotaje) {
        if (g_fallos == 0) {
            printf("\033[31mLA BATERÍA NO DETECTA EL SABOTAJE %d — "
                   "no está probando lo que dice\033[0m\n", sabotaje);
            return 1;
        }
        printf("\033[32mel sabotaje %d se detecta (%d fallos)\033[0m\n",
               sabotaje, g_fallos);
        return 0;
    }
    return g_fallos ? 1 : 0;
}
