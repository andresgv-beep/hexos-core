/*
 * Batería del perfil, la recuperación previa y el MemoryDelta (E3, pasos 2-3).
 *
 * Las dos propiedades que hay que demostrar aquí no son "funciona", son
 * "no hace lo que no debe":
 *   · el perfil solo consume CONFIRMADO — candidatos y legacy no salen,
 *   · recuperar y leer un delta NO ESCRIBEN, y se comprueba byte a byte.
 *
 * Sabotajes (-DHERA_SABOTAJE=N), en el rango 20+ para no chocar con los del
 * almacén:
 *   20  el perfil también consume candidatos
 *   21  recuperar deja una anotación en el diario
 *   22  el delta se aplica en vez de solo ensayarse
 *   23  el parser vuelve a ser laxo (acepta lo que no esta en el esquema)
 */

#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif
#include "hera_profile.h"
#include "hera_delta.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

static int g_fallos, g_pruebas;
static char g_base[512], g_dir[700];

static void ok(bool cond, const char *nombre, const char *detalle) {
    g_pruebas++;
    if (cond) printf("  \033[32m✓\033[0m %s\n", nombre);
    else { g_fallos++; printf("  \033[31m✗ %s\033[0m — %s\n", nombre, detalle); }
}

static void perfil_nuevo(const char *nombre) {
    snprintf(g_dir, sizeof(g_dir), "%s/%s", g_base, nombre);
    char cmd[800];
    snprintf(cmd, sizeof(cmd), "rm -rf '%s'", g_dir);
    if (system(cmd) != 0) { /* no existía */ }
    mkdir(g_dir, 0755);
    setenv("HELIOS_HOME", g_dir, 1);
    setenv("HERA_TS_FIJO", "1700000000", 1);
    hera_store_abrir();
}

/* Copia del diario en memoria, para comparar antes/después byte a byte. */
static char *leer_diario(size_t *out_len) {
    FILE *f = fopen(hera_store_ruta(), "rb");
    if (!f) { *out_len = 0; return NULL; }
    fseek(f, 0, SEEK_END);
    const long n = ftell(f);
    fseek(f, 0, SEEK_SET);
    char *buf = malloc((size_t)n + 1);
    if (buf) {
        if (fread(buf, 1, (size_t)n, f) != (size_t)n) { /* corto: se compara igual */ }
        buf[n] = '\0';
    }
    fclose(f);
    *out_len = (size_t)n;
    return buf;
}

/* Un perfil con un confirmado, un candidato y legacy en cuarentena. */
static void poblar(void) {
    char u[HERA_ID_MAX], u2[HERA_ID_MAX], c[HERA_ID_MAX], f[HERA_ID_MAX];

    hera_store_dijo("guarda esto: me llamo Andrés", u, sizeof(u));
    hera_store_registrar("yo/nombre", "Andrés", "Se llama Andrés",
                         u, u, NULL, 0);

    hera_store_dijo("guarda esto: mi perro se llama Rufo", u2, sizeof(u2));
    hera_store_registrar("perro/nombre", "Rufo", "Su perro se llama Rufo",
                         u2, u2, NULL, 0);

    /* Un candidato sin confirmar: no debe salir por ningún lado. */
    hera_store_dijo("creo que me mudo a Girona", c, sizeof(c));
    hera_store_proponer("yo/ciudad", "Girona", "Vive en Girona", c,
                        f, sizeof(f));

    /* Y memoria legacy envenenada en cuarentena. */
    char ruta[900];
    snprintf(ruta, sizeof(ruta), "%s/facts.md", g_dir);
    FILE *g = fopen(ruta, "w");
    fputs("- La persona se llama Ana y vive en Bilbao.\n"
          "- Helios nació en Bilbao.\n", g);
    fclose(g);
    hera_store_importar_legacy();
}

/* ---------------------------------------------------------------------- */

static void prueba_perfil_derivado(void) {
    printf("\n[1] el perfil es una vista derivada, y solo de confirmados\n");
    perfil_nuevo("m1");
    poblar();

    hera_perfil_t p;
    hera_perfil_derivar(&p);

    ok(strcmp(p.nombre, "Andrés") == 0,
       "el nombre sale del yo/nombre confirmado", p.nombre);
    ok(p.propias_n == 1, "una relación propia", "cuenta distinta");
    ok(p.ajenas_n == 1, "una ajena (el perro)", "cuenta distinta");
    ok(p.propias_n == 1 && strcmp(p.propias[0].predicado, "nombre") == 0,
       "la clave se lee por sus dos mitades: sujeto y predicado",
       "no se parte la clave");
    ok(p.propias_n == 1 && p.propias[0].evidencia[0] != '\0',
       "cada relación conserva con qué palabras se supo", "sin cita");

    bool candidato_dentro = false, legacy_dentro = false;
    for (size_t i = 0; i < p.propias_n; i++) {
        if (strcmp(p.propias[i].valor, "Girona") == 0) candidato_dentro = true;
        if (strstr(p.propias[i].valor, "Ana")) legacy_dentro = true;
    }
    for (size_t i = 0; i < p.ajenas_n; i++)
        if (strstr(p.ajenas[i].valor, "Ana") || strstr(p.ajenas[i].valor, "Helios"))
            legacy_dentro = true;
    ok(!candidato_dentro, "el candidato no está en el perfil", "se coló");
    ok(!legacy_dentro, "el legacy en cuarentena tampoco", "la contaminación entró");

    /* Derivar dos veces da lo mismo: no hay estado escondido. */
    hera_perfil_t q;
    hera_perfil_derivar(&q);
    ok(memcmp(&p, &q, sizeof(p)) == 0,
       "derivar dos veces da exactamente lo mismo", "hay estado escondido");

    /* Y tras releer el diario, también: la vista no guarda nada propio. */
    hera_store_cerrar();
    hera_store_abrir();
    hera_perfil_t r;
    hera_perfil_derivar(&r);
    ok(memcmp(&p, &r, sizeof(p)) == 0,
       "y sobrevive a un reinicio sin segundo almacén",
       "el perfil no se deriva del diario");
}

static void prueba_recuperacion_lectora(void) {
    printf("\n[2] la recuperación previa es determinista y NO escribe\n");
    perfil_nuevo("m2");
    poblar();

    size_t antes_n = 0;
    char *antes = leer_diario(&antes_n);

    char buf1[4096], buf2[4096];
    const size_t n1 = hera_recuperar(buf1, sizeof(buf1), 3000);
    const size_t n2 = hera_recuperar(buf2, sizeof(buf2), 3000);

    ok(n1 > 0, "devuelve algo con hechos confirmados", "vino vacío");
    ok(n1 == n2 && memcmp(buf1, buf2, n1) == 0,
       "dos llamadas dan exactamente el mismo texto", "no es determinista");

    size_t desp_n = 0;
    char *desp = leer_diario(&desp_n);
    ok(antes_n == desp_n && antes && desp &&
       memcmp(antes, desp, antes_n) == 0,
       "el diario no ha cambiado ni un byte", "recuperar escribió algo");
    free(antes); free(desp);

    ok(strstr(buf1, "Andrés") != NULL, "el hecho confirmado está", "falta");
    ok(strstr(buf1, "Girona") == NULL,
       "el candidato NO llega al prompt", "el candidato se coló al prompt");
    ok(strstr(buf1, "Ana") == NULL && strstr(buf1, "Bilbao") == NULL,
       "la identidad legacy inventada tampoco",
       "la contaminación llegó al prompt");

    /* El recorte corta por hecho entero. */
    char corto[4096];
    const size_t nc = hera_recuperar(corto, sizeof(corto), 120);
    ok(nc <= 120, "respeta el presupuesto", "se pasó");
    ok(nc == 0 || corto[nc - 1] == '\n',
       "y corta por hecho entero, no a media frase", "cortó a mitad");

    /* Perfil vacío: mejor callar que inventarse quién eres. */
    perfil_nuevo("m2b");
    ok(hera_recuperar(buf1, sizeof(buf1), 3000) == 0,
       "un perfil nuevo no recupera nada", "se inventó un perfil");
}

static void prueba_delta(void) {
    printf("\n[3] el MemoryDelta se valida entero y NO se aplica\n");
    perfil_nuevo("m3");
    poblar();

    /* Para que el caso de polaridad se rechace POR LA POLARIDAD y no por
     * literalidad, la evidencia tiene que hablar de gustos. Si no, la prueba
     * pasaría por el motivo equivocado. */
    char ug[HERA_ID_MAX];
    hera_store_dijo("me gusta el café", ug, sizeof(ug));

    size_t antes_n = 0;
    char *antes = leer_diario(&antes_n);

    /* Un delta con de todo: una válida, una sin evidencia, una de sujeto
     * ajeno, una con la polaridad al revés y un verbo inventado. */
    const char *json =
        "{\"memory_delta\":["
        "{\"op\":\"proponer\",\"clave\":\"perro/color\",\"valor\":\"Rufo\","
        " \"texto\":\"Su perro se llama Rufo\",\"evidencia\":\"u2\"},"
        "{\"op\":\"proponer\",\"clave\":\"ana/ciudad\",\"valor\":\"Bilbao\","
        " \"texto\":\"Ana vive en Bilbao\",\"evidencia\":\"u1\"},"
        "{\"op\":\"proponer\",\"clave\":\"yo/gusto\","
        " \"valor\":\"no me gusta el café\","
        " \"texto\":\"No le gusta el café\",\"evidencia\":\"u4\"}"
        "]}";

    hera_delta_t d;
    ok(hera_delta_leer(json, &d), "el delta se lee", "no se pudo leer");
    ok(d.n == 3, "tres operaciones", "cuenta distinta");
    ok(d.aceptables == 1, "solo una pasaría las reglas", "cuenta distinta");
    ok(d.ops[0].veredicto == HERA_OK, "la buena pasa",
       hera_veredicto_nombre(d.ops[0].veredicto));
    ok(d.ops[1].veredicto == HERA_RECHAZO_SUJETO_AJENO,
       "\"Ana vive en Bilbao\" se rechaza por sujeto ajeno",
       hera_veredicto_nombre(d.ops[1].veredicto));
    ok(d.ops[2].veredicto == HERA_RECHAZO_POLARIDAD,
       "la polaridad al revés se rechaza",
       hera_veredicto_nombre(d.ops[2].veredicto));

    /* LA propiedad de este paso. */
    size_t desp_n = 0;
    char *desp = leer_diario(&desp_n);
    ok(antes_n == desp_n && antes && desp && memcmp(antes, desp, antes_n) == 0,
       "el diario no ha cambiado ni un byte: leer un delta no aplica nada",
       "el delta se aplicó");
    free(antes); free(desp);

    hera_hecho_t hs[32];
    bool coló = false;
    const size_t t = hera_store_todos(hs, 32);
    for (size_t i = 0; i < t; i++)
        if (strcmp(hs[i].clave, "perro/color") == 0) coló = true;
    ok(!coló, "ni la operación válida se ha escrito: aplicar no existe aún",
       "la operación válida se aplicó sola");

    /* Una llave dentro de un string no puede partir los objetos. */
    const char *con_llave =
        "{\"memory_delta\":["
        "{\"op\":\"proponer\",\"clave\":\"perro/nombre\",\"valor\":\"Rufo\","
        " \"texto\":\"lo escribe así: { Rufo }\",\"evidencia\":\"u2\"}"
        "]}";
    hera_delta_t d2;
    hera_delta_leer(con_llave, &d2);
    ok(d2.n == 1 && strcmp(d2.ops[0].valor, "Rufo") == 0,
       "una llave dentro de un texto no parte el troceo",
       "el parser contó llaves a lo bruto");

    /* Un delta roto no puede pasar por vacío. */
    hera_delta_t d3;
    const bool leido = hera_delta_leer(
        "{\"memory_delta\":[{\"op\":\"proponer\",\"clave\":\"a/b\"", &d3);
    ok(!leido && !d3.bien_formado,
       "un objeto sin cerrar se denuncia, no pasa por delta vacío",
       "un delta corrupto pasó por bueno");

    hera_delta_t d4;
    ok(!hera_delta_leer("{\"otra_cosa\":[]}", &d4),
       "un JSON sin memory_delta se rechaza", "aceptó cualquier cosa");
}

/* Esquema todo o nada: cualquier violación tumba el delta ENTERO. */
static void prueba_parser_estricto(void) {
    printf("\n[4] el esquema es todo o nada\n");
    perfil_nuevo("m4");
    poblar();

    const char *EV = "\"evidencia\":\"u2\"";
    char json[8192];
    hera_delta_t d;

    struct { const char *nombre; const char *cuerpo; } malos[] = {
      {"el array no se cierra",
       "{\"memory_delta\":[{\"op\":\"proponer\",\"clave\":\"a/b\","
       "\"valor\":\"Rufo\",\"evidencia\":\"u2\"}"},
      {"una clave fuera del esquema",
       "{\"memory_delta\":[{\"op\":\"proponer\",\"clave\":\"perro/x\","
       "\"valor\":\"Rufo\",\"evidencia\":\"u2\",\"prioridad\":\"alta\"}]}"},
      {"un verbo inventado",
       "{\"memory_delta\":[{\"op\":\"olvidar\",\"clave\":\"perro/x\","
       "\"valor\":\"Rufo\",\"evidencia\":\"u2\"}]}"},
      {"una operación sin \"op\"",
       "{\"memory_delta\":[{\"clave\":\"perro/x\",\"valor\":\"Rufo\","
       "\"evidencia\":\"u2\"}]}"},
      {"a una proponer le falta la evidencia",
       "{\"memory_delta\":[{\"op\":\"proponer\",\"clave\":\"perro/x\","
       "\"valor\":\"Rufo\"}]}"},
      {"a una confirmar le falta la confirmación",
       "{\"memory_delta\":[{\"op\":\"confirmar\",\"id\":\"f1\"}]}"},
      {"un elemento que no es objeto",
       "{\"memory_delta\":[\"proponer\"]}"},
      {"una clave repetida",
       "{\"memory_delta\":[{\"op\":\"proponer\",\"clave\":\"perro/x\","
       "\"clave\":\"otro/y\",\"valor\":\"Rufo\",\"evidencia\":\"u2\"}]}"},
      {"basura detrás del delta",
       "{\"memory_delta\":[]} y aquí lo que sea"},
      {"el delta no es un objeto",
       "[{\"op\":\"proponer\"}]"},
      /* Aísla la guarda del cierre del array: aquí el OBJETO sí cierra, así
       * que si no se exigiera el ']' el delta pasaría entero por bueno. Sin
       * este caso, el fixture de arriba lo caza la guarda del objeto y la del
       * array quedaría sin probar. */
      {"el array no cierra aunque el objeto sí",
       "{\"memory_delta\":[{\"op\":\"proponer\",\"clave\":\"perro/x\","
       "\"valor\":\"Rufo\",\"evidencia\":\"u2\"}}"},
      {NULL, NULL}
    };
    (void)EV;
    for (int i = 0; malos[i].nombre; i++) {
        const bool leido = hera_delta_leer(malos[i].cuerpo, &d);
        ok(!leido && !d.bien_formado && d.n == 0 && d.motivo[0],
           malos[i].nombre, leido ? "se aceptó" : "sin motivo o con ops sueltas");
    }

    /* Más de HERA_DELTA_OPS_MAX: antes se truncaba en silencio y el delta
     * pasaba por bueno con las 32 primeras. */
    int n = snprintf(json, sizeof(json), "{\"memory_delta\":[");
    for (int i = 0; i < HERA_DELTA_OPS_MAX + 1; i++)
        n += snprintf(json + n, sizeof(json) - n,
                      "%s{\"op\":\"proponer\",\"clave\":\"perro/p%d\","
                      "\"valor\":\"Rufo\",%s}", i ? "," : "", i, EV);
    snprintf(json + n, sizeof(json) - n, "]}");
    ok(!hera_delta_leer(json, &d) && d.n == 0,
       "más de 32 operaciones se rechaza, no se trunca en silencio",
       d.bien_formado ? "pasó por bueno" : "dejó ops sueltas");

    /* Un valor más largo de lo que cabe: recortarlo sería guardar otro dato. */
    n = snprintf(json, sizeof(json),
                 "{\"memory_delta\":[{\"op\":\"proponer\","
                 "\"clave\":\"perro/largo\",\"valor\":\"");
    for (int i = 0; i < HERA_VALOR_MAX + 50; i++) json[n++] = 'x';
    snprintf(json + n, sizeof(json) - n, "\",%s}]}", EV);
    ok(!hera_delta_leer(json, &d),
       "un valor que no cabe se rechaza, no se trunca",
       "se truncó en silencio");

    /* La trampa del parser viejo: buscaba "memory_delta" con strstr, así que
     * se lo habría comido escrito DENTRO del texto de un recuerdo. */
    ok(!hera_delta_leer(
        "{\"nota\":\"escribe un \\\"memory_delta\\\" en el informe\"}", &d),
       "\"memory_delta\" dentro de un texto no cuenta como el array",
       "el parser lo confundió con la clave de verdad");

    /* Y lo válido sigue siéndolo. */
    snprintf(json, sizeof(json),
             "{\"version\":\"1\",\"memory_delta\":[{\"op\":\"proponer\","
             "\"clave\":\"perro/color\",\"valor\":\"Rufo\","
             "\"texto\":\"Su perro es Rufo\",%s}]}", EV);
    ok(hera_delta_leer(json, &d) && d.n == 1 && d.bien_formado,
       "un delta correcto con campos de más ARRIBA sigue valiendo", d.motivo);
    ok(hera_delta_leer("{\"memory_delta\":[]}", &d) && d.n == 0,
       "y un delta vacío es válido: no proponer nada es una respuesta",
       d.motivo);
}

/* ---------------------------------------------------------------------- */

int main(int argc, char **argv) {
    int sabotaje = 0;
    for (int i = 1; i < argc; i++)
        if (!strcmp(argv[i], "--sabotaje") && i + 1 < argc)
            sabotaje = atoi(argv[++i]);

    const char *tmp = getenv("TMPDIR");
    snprintf(g_base, sizeof(g_base), "%s/hera_e3_mente",
             tmp && *tmp ? tmp : "/tmp");
    mkdir(g_base, 0755);

    if (sabotaje) printf("\n\033[33mSABOTAJE %d activo — "
                         "la batería DEBE fallar\033[0m\n", sabotaje);

    prueba_perfil_derivado();
    prueba_recuperacion_lectora();
    prueba_delta();
    prueba_parser_estricto();

    printf("\n%d pruebas · %d fallos\n", g_pruebas, g_fallos);
    if (sabotaje) {
        if (g_fallos == 0) {
            printf("\033[31mLA BATERÍA NO DETECTA EL SABOTAJE %d\033[0m\n",
                   sabotaje);
            return 1;
        }
        printf("\033[32mel sabotaje %d se detecta (%d fallos)\033[0m\n",
               sabotaje, g_fallos);
        return 0;
    }
    return g_fallos ? 1 : 0;
}
