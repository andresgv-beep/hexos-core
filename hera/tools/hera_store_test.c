/*
 * Batería de la barrera de E3.
 *
 * Cada prueba corre en un perfil recién creado (HELIOS_HOME propio) para que
 * ninguna herede el estado de la anterior — que es, además, uno de los puntos
 * que hay que demostrar.
 *
 * Con `--sabotaje N` se anuncia que el binario está roto a propósito y la
 * batería DEBE fallar. Una prueba que pasa contra un almacén saboteado no
 * está probando nada. Los sabotajes (compilados con -DHERA_SABOTAJE=N):
 *   1  el respaldo de la evidencia siempre dice que sí
 *   2  corregir vuelve a ser dos escrituras (el bug de la atomicidad)
 *   3  los candidatos se cuelan entre los confirmados
 *   4  no se comprueba de quién se dijo el dato
 *   5  la polaridad se ignora (bolsa de palabras pura)
 *   6  confirmar no exige intervención registrada de la persona
 *   7  la memoria legacy envenenada entra como autoridad
 */

#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif
#include "hera_store.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <unistd.h>

static int g_fallos, g_pruebas;
static char g_base[512];
static char g_dir[700];

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
    snprintf(g_dir, sizeof(g_dir), "%s/%s", g_base, nombre);
    char cmd[800];
    snprintf(cmd, sizeof(cmd), "rm -rf '%s'", g_dir);
    if (system(cmd) != 0) { /* no existía: perfecto */ }
    mkdir(g_dir, 0755);
    setenv("HELIOS_HOME", g_dir, 1);
    setenv("HERA_TS_FIJO", "1700000000", 1);
    hera_store_abrir();
}

/* ---------------------------------------------------------------------- */

/* "Ana vive en Bilbao": el hecho estrella que tiene que ser imposible. */
static void prueba_sin_evidencia(void) {
    printf("\n[1] ningún recuerdo nace sin evidencia\n");
    perfil("p1");

    hera_veredicto_t v = hera_store_proponer("ana/ciudad", "Bilbao",
        "Ana vive en Bilbao", NULL, NULL, 0);
    ok(v == HERA_RECHAZO_SIN_EVIDENCIA, "sin citar nada dicho → rechazado",
       hera_veredicto_nombre(v));

    v = hera_store_proponer("ana/ciudad", "Bilbao", "Ana vive en Bilbao",
                            "u99", NULL, 0);
    ok(v == HERA_RECHAZO_SIN_EVIDENCIA,
       "citando una evidencia inventada → rechazado",
       hera_veredicto_nombre(v));

    /* La persona habla de Ana, pero nunca de Bilbao. */
    char u[HERA_ID_MAX];
    hera_store_dijo("Ana es mi hermana y trabaja de enfermera", u, sizeof(u));
    v = hera_store_proponer("ana/ciudad", "Bilbao", "Ana vive en Bilbao",
                            u, NULL, 0);
    ok(v == HERA_RECHAZO_NO_LITERAL,
       "citando algo real que NO dice Bilbao → rechazado",
       hera_veredicto_nombre(v));

    v = hera_store_proponer("ana/oficio", "enfermera",
                            "Su hermana Ana es enfermera", u, NULL, 0);
    ok(v == HERA_OK, "el dato que sí está en sus palabras → aceptado",
       hera_veredicto_nombre(v));

    hera_hecho_t hs[16];
    ok(hera_store_confirmados(hs, 16) == 0,
       "y aun así entra como candidato, no como hecho", "se coló al prompt");
}

/* Palabra completa, no subcadena: "Ana" no vale dentro de "manzana". */
static void prueba_frontera_de_palabra(void) {
    printf("\n[2] la evidencia se mide por palabra, no por subcadena\n");
    perfil("p2");

    char u[HERA_ID_MAX];
    hera_store_dijo("me comí una manzana en el parque", u, sizeof(u));
    hera_veredicto_t v = hera_store_proponer("yo/nombre", "Ana",
                                             "Se llama Ana", u, NULL, 0);
    ok(v == HERA_RECHAZO_NO_LITERAL,
       "\"Ana\" escondida dentro de \"manzana\" → rechazado",
       hera_veredicto_nombre(v));

    hera_store_dijo("me llamo Ana", u, sizeof(u));
    v = hera_store_proponer("yo/nombre", "Ana", "Se llama Ana", u, NULL, 0);
    ok(v == HERA_OK, "\"Ana\" como palabra suelta → aceptado",
       hera_veredicto_nombre(v));
}

/* EL SUJETO. "Luis vive en Bilbao" no autoriza ana/ciudad = Bilbao. */
static void prueba_sujeto(void) {
    printf("\n[3] el dato tiene que haberse dicho DE ese sujeto\n");
    perfil("p3");

    char u[HERA_ID_MAX];
    hera_store_dijo("Luis vive en Bilbao", u, sizeof(u));
    hera_veredicto_t v = hera_store_proponer("ana/ciudad", "Bilbao",
        "Ana vive en Bilbao", u, NULL, 0);
    ok(v == HERA_RECHAZO_SUJETO_AJENO,
       "\"Luis vive en Bilbao\" NO autoriza ana/ciudad = Bilbao",
       hera_veredicto_nombre(v));

    v = hera_store_proponer("luis/ciudad", "Bilbao", "Luis vive en Bilbao",
                            u, NULL, 0);
    ok(v == HERA_OK, "pero sí autoriza luis/ciudad = Bilbao",
       hera_veredicto_nombre(v));

    /* Dos personas en el mismo mensaje, en frases distintas: el troceo por
     * frases es lo que impide cruzar los datos. */
    hera_store_dijo("Ana es mi hermana. Luis vive en Girona", u, sizeof(u));
    v = hera_store_proponer("ana/ciudad", "Girona", "Ana vive en Girona",
                            u, NULL, 0);
    ok(v == HERA_RECHAZO_SUJETO_AJENO,
       "en dos frases, el dato de una no salta a la otra",
       hera_veredicto_nombre(v));

    /* El sujeto reservado: quien escribe no se nombra a sí mismo. */
    hera_store_dijo("vivo en Sevilla desde hace años", u, sizeof(u));
    v = hera_store_proponer("yo/ciudad", "Sevilla", "Vive en Sevilla",
                            u, NULL, 0);
    ok(v == HERA_OK, "\"yo\" no necesita nombrarse: lo acredita ser el autor",
       hera_veredicto_nombre(v));
}

/* LA POLARIDAD. "me gusta el café" no autoriza "no me gusta el café". */
static void prueba_polaridad(void) {
    printf("\n[4] la negación corta no se pierde\n");
    perfil("p4");

    char u[HERA_ID_MAX];
    hera_store_dijo("me gusta el café", u, sizeof(u));
    hera_veredicto_t v = hera_store_proponer("yo/gusto", "no me gusta el café",
        "No le gusta el café", u, NULL, 0);
    ok(v == HERA_RECHAZO_POLARIDAD,
       "\"me gusta el café\" NO autoriza \"no me gusta el café\"",
       hera_veredicto_nombre(v));

    v = hera_store_proponer("yo/gusto", "me gusta el café",
                            "Le gusta el café", u, NULL, 0);
    ok(v == HERA_OK, "el mismo dato con la polaridad correcta → aceptado",
       hera_veredicto_nombre(v));

    /* Y al revés: de una negación no sale una afirmación. */
    perfil("p4b");
    hera_store_dijo("no me gusta el té", u, sizeof(u));
    v = hera_store_proponer("yo/gusto", "me gusta el té", "Le gusta el té",
                            u, NULL, 0);
    ok(v == HERA_RECHAZO_POLARIDAD,
       "y de \"no me gusta el té\" no sale \"me gusta el té\"",
       hera_veredicto_nombre(v));
}

/* Proponer no puede ascender; confirmar exige que la persona interviniera. */
static void prueba_autoridad(void) {
    printf("\n[5] proponer y confirmar son cosas distintas\n");
    perfil("p5");

    char u[HERA_ID_MAX], f[HERA_ID_MAX];
    hera_store_dijo("mi perro se llama Byteazul", u, sizeof(u));
    ok(hera_store_proponer("perro/nombre", "Byteazul", "Su perro es Byteazul",
                           u, f, sizeof(f)) == HERA_OK,
       "la extracción del modelo entra", "no entró");

    hera_hecho_t hs[16];
    ok(hera_store_confirmados(hs, 16) == 0,
       "no hay forma de pedir por esa puerta que nazca confirmado",
       "nació confirmado");

    hera_veredicto_t v = hera_store_confirmar(f, NULL);
    ok(v == HERA_RECHAZO_SIN_CONFIRMACION,
       "confirmar sin intervención registrada → rechazado",
       hera_veredicto_nombre(v));

    v = hera_store_confirmar(f, "u42");
    ok(v == HERA_RECHAZO_SIN_CONFIRMACION,
       "citando una intervención inventada → rechazado",
       hera_veredicto_nombre(v));
    ok(hera_store_confirmados(hs, 16) == 0,
       "y sigue sin ser un hecho", "ascendió igualmente");

    char c[HERA_ID_MAX];
    hera_store_dijo("sí, guárdalo", c, sizeof(c));
    ok(hera_store_confirmar(f, c) == HERA_OK, "con su \"sí\" registrado, sube",
       "no subió");

    const size_t n = hera_store_confirmados(hs, 16);
    ok(n == 1 && strcmp(hs[0].confirmacion, c) == 0,
       "y el hecho guarda CON QUÉ palabras se confirmó",
       "no consta la confirmación");

    /* La otra puerta: petición explícita en un paso, pero hay que nombrarla. */
    perfil("p5b");
    hera_store_dijo("guarda en memoria: mi gato se llama Rufo", u, sizeof(u));
    v = hera_store_registrar("gato/nombre", "Rufo", "Su gato es Rufo",
                             u, NULL, NULL, 0);
    ok(v == HERA_RECHAZO_SIN_CONFIRMACION,
       "registrar sin nombrar la petición → rechazado",
       hera_veredicto_nombre(v));
    v = hera_store_registrar("gato/nombre", "Rufo", "Su gato es Rufo",
                             u, u, NULL, 0);
    ok(v == HERA_OK, "nombrándola, entra confirmado de una",
       hera_veredicto_nombre(v));
}

/* Una corrección sustituye y se puede auditar. */
static void prueba_correccion(void) {
    printf("\n[6] corregir sustituye, y la transición se audita\n");
    perfil("p6");

    char u1[HERA_ID_MAX], u2[HERA_ID_MAX], f1[HERA_ID_MAX], f2[HERA_ID_MAX];
    hera_store_dijo("guarda esto: mi perro se llama Byteazul", u1, sizeof(u1));
    hera_store_registrar("perro/nombre", "Byteazul", "Su perro es Byteazul",
                         u1, u1, f1, sizeof(f1));

    hera_store_dijo("me equivoqué, el perro se llama Rufo", u2, sizeof(u2));
    hera_veredicto_t v = hera_store_corregir("perro/nombre", "Rufo",
        "Su perro se llama Rufo", u2, u2, f2, sizeof(f2));
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
        if (strcmp(hs[i].id, f1) == 0 && hs[i].estado == HERA_SUSTITUIDO &&
            strcmp(hs[i].sustituido_por, f2) == 0) cadena = true;
    ok(cadena, "el viejo queda marcado y apunta al nuevo",
       "no hay puntero de sustitución");

    const char *ev = hera_store_evidencia(u2);
    ok(ev && strstr(ev, "Rufo") != NULL,
       "la evidencia del cambio es recuperable", "no se puede citar el porqué");

    /* Corregir una clave de la que nunca se supo nada. La evidencia tiene que
     * ser válida para que el rechazo sea por eso y no por el filtro de sujeto
     * — si no, la prueba pasaría por el motivo equivocado. */
    char u3[HERA_ID_MAX];
    hera_store_dijo("el gato se llama Rufo", u3, sizeof(u3));
    v = hera_store_corregir("gato/nombre", "Rufo", "Su gato es Rufo",
                            u3, u3, NULL, 0);
    ok(v == HERA_RECHAZO_DESCONOCIDO,
       "corregir lo que no existe → rechazado (con evidencia válida)",
       hera_veredicto_nombre(v));
}

/* ATOMICIDAD: una caída a mitad de la corrección no deja dos confirmados. */
static void prueba_corte_a_media_correccion(void) {
    printf("\n[7] una caída a media corrección no deja dos confirmados\n");
    perfil("p7");

    char u1[HERA_ID_MAX], u2[HERA_ID_MAX];
    hera_store_dijo("guarda esto: mi perro se llama Byteazul", u1, sizeof(u1));
    hera_store_registrar("perro/nombre", "Byteazul", "Su perro es Byteazul",
                         u1, u1, NULL, 0);
    hera_store_dijo("me equivoqué, el perro se llama Rufo", u2, sizeof(u2));

    char ruta[900];
    snprintf(ruta, sizeof(ruta), "%s", hera_store_ruta());
    hera_store_corregir("perro/nombre", "Rufo", "Su perro se llama Rufo",
                        u2, u2, NULL, 0);

    /* El proceso muere justo antes de terminar de escribir: se corta el
     * último byte del fichero. Si la corrección fuese dos escrituras, la
     * primera ya estaría entera en disco y el hecho nuevo sobreviviría sin
     * que cayera el viejo. */
    FILE *f = fopen(ruta, "rb");
    fseek(f, 0, SEEK_END);
    const long tam = ftell(f);
    fclose(f);
    ok(truncate(ruta, tam - 1) == 0, "se simula la caída (último byte fuera)",
       "no se pudo truncar");

    hera_store_cerrar();
    hera_store_abrir();

    hera_hecho_t hs[16];
    const size_t n = hera_store_confirmados(hs, 16);
    ok(n == 1, "tras reiniciar sigue habiendo UN solo hecho vigente",
       "quedaron dos confirmados contradiciéndose");
    ok(n == 1 && strcmp(hs[0].valor, "Byteazul") == 0,
       "y es el de antes: la corrección a medias no ocurrió",
       "sobrevivió media corrección");
}

/* Los candidatos no son hechos. */
static void prueba_candidatos(void) {
    printf("\n[8] los candidatos no entran al prompt\n");
    perfil("p8");

    char u[HERA_ID_MAX], f[HERA_ID_MAX], c[HERA_ID_MAX];
    hera_store_dijo("creo que me mudo a Girona en otoño", u, sizeof(u));
    hera_store_proponer("yo/ciudad", "Girona", "Se muda a Girona", u,
                        f, sizeof(f));

    hera_hecho_t hs[16];
    ok(hera_store_confirmados(hs, 16) == 0,
       "un candidato no aparece entre los confirmados", "se coló");
    ok(hera_store_todos(hs, 16) == 1,
       "pero sigue guardado para poder confirmarlo luego", "se perdió");

    hera_store_dijo("sí, es correcto", c, sizeof(c));
    ok(hera_store_confirmar(f, c) == HERA_OK, "la persona lo confirma", "falló");
    ok(hera_store_confirmados(hs, 16) == 1, "y entonces sí es un hecho",
       "no ascendió");
}

/* Reiniciar conserva exactamente el estado confirmado. */
static void prueba_reinicio(void) {
    printf("\n[9] reiniciar conserva exactamente el estado confirmado\n");
    perfil("p9");

    char u[HERA_ID_MAX], c[HERA_ID_MAX];
    hera_store_dijo("guarda esto: mi perro se llama Byteazul y vivo en Sevilla",
                    u, sizeof(u));
    hera_store_registrar("perro/nombre", "Byteazul", "Su perro es Byteazul",
                         u, u, NULL, 0);
    hera_store_proponer("yo/ciudad", "Sevilla", "Vive en Sevilla", u,
                        c, sizeof(c));
    hera_store_dijo("perdona, el perro es Rufo", u, sizeof(u));
    hera_store_corregir("perro/nombre", "Rufo", "Su perro es Rufo", u, u,
                        NULL, 0);

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
                  strcmp(antes[i].confirmacion, desp[i].confirmacion) == 0 &&
                  antes[i].estado == desp[i].estado;
    ok(iguales, "y son exactamente los mismos, con su confirmación",
       "algo cambió al releer");

    bool candidato_fuera = true, sustituido_fuera = true;
    for (size_t i = 0; i < nd; i++) {
        if (strcmp(desp[i].id, c) == 0) candidato_fuera = false;
        if (strcmp(desp[i].valor, "Byteazul") == 0) sustituido_fuera = false;
    }
    ok(candidato_fuera, "el candidato sigue sin ser un hecho tras reiniciar",
       "ascendió solo");
    ok(sustituido_fuera, "el corregido no vuelve de entre los muertos",
       "el sustituido resucitó");
}

/* Un perfil vacío no recibe datos de otro. */
static void prueba_aislamiento(void) {
    printf("\n[10] un perfil vacío no hereda nada de otro\n");

    perfil("p10a");
    char u[HERA_ID_MAX];
    hera_store_dijo("guarda esto: mi perro se llama Byteazul", u, sizeof(u));
    hera_store_registrar("perro/nombre", "Byteazul", "Su perro es Byteazul",
                         u, u, NULL, 0);
    hera_hecho_t hs[16];
    ok(hera_store_confirmados(hs, 16) == 1, "el perfil A sabe su hecho", "no");

    perfil("p10b");
    ok(hera_store_confirmados(hs, 16) == 0,
       "el perfil B arranca sin hechos", "heredó memoria ajena");
    ok(hera_store_evidencia("u1") == NULL,
       "y no puede citar evidencias del otro perfil",
       "las evidencias cruzan perfiles");

    hera_veredicto_t v = hera_store_proponer("perro/nombre", "Byteazul",
        "Su perro es Byteazul", "u1", NULL, 0);
    ok(v == HERA_RECHAZO_SIN_EVIDENCIA,
       "reusar el id del otro perfil no cuela", hera_veredicto_nombre(v));
}

/* La memoria legacy entra en cuarentena, envenenada incluida. */
static void prueba_legacy_en_cuarentena(void) {
    printf("\n[11] la memoria legacy entra en cuarentena, no como autoridad\n");
    perfil("p11");

    char ruta[900];
    snprintf(ruta, sizeof(ruta), "%s/facts.md", g_dir);
    FILE *f = fopen(ruta, "w");
    /* Dos de estas son la contaminación conocida de facts.md: un hecho falso
     * y una identidad inventada para el propio Helios. */
    fputs("- Se llama Andrés y construye un motor de inferencia.\n"
          "- La persona vive en Bilbao y se llama Ana.\n"
          "- Helios nació en Bilbao y tiene una hermana.\n", f);
    fclose(f);
    snprintf(ruta, sizeof(ruta), "%s/candidates.md", g_dir);
    f = fopen(ruta, "w");
    fputs("- Puede que esté escribiendo un libro.\n", f);
    fclose(f);

    hera_store_abrir();
    const size_t n = hera_store_importar_legacy();
    ok(n == 4, "importa las cuatro líneas", "cuenta distinta");

    hera_hecho_t hs[16];
    ok(hera_store_confirmados(hs, 16) == 0,
       "NINGUNA gobierna nada: cero confirmados", "la contaminación mandó");

    const size_t t = hera_store_todos(hs, 16);
    size_t en_cuarentena = 0;
    for (size_t i = 0; i < t; i++)
        if (strcmp(hs[i].origen, "legacy") == 0 &&
            hs[i].estado == HERA_CANDIDATO &&
            hs[i].evidencia[0] == '\0') en_cuarentena++;
    ok(en_cuarentena == 4,
       "las cuatro quedan como candidatos legacy sin cita, visibles",
       "alguna se coló con otro estado");

    /* La identidad inventada sigue ahí para poder revisarla, pero no habla. */
    bool identidad_muda = true;
    const size_t nc = hera_store_confirmados(hs, 16);
    for (size_t i = 0; i < nc; i++)
        if (strstr(hs[i].valor, "Helios") || strstr(hs[i].valor, "Ana"))
            identidad_muda = false;
    ok(identidad_muda, "la identidad inventada no puede entrar al prompt",
       "la identidad falsa gobierna");

    ok(hera_store_importar_legacy() == 0, "importar dos veces no duplica",
       "duplicó");
    hera_store_cerrar();
    hera_store_abrir();
    ok(hera_store_importar_legacy() == 0, "ni siquiera tras reiniciar",
       "duplicó tras reiniciar");
    ok(hera_store_confirmados(hs, 16) == 0,
       "y tras reiniciar sigue sin gobernar nada", "resucitó como autoridad");
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
    prueba_sujeto();
    prueba_polaridad();
    prueba_autoridad();
    prueba_correccion();
    prueba_corte_a_media_correccion();
    prueba_candidatos();
    prueba_reinicio();
    prueba_aislamiento();
    prueba_legacy_en_cuarentena();

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
