/*
 * HERA — cola durable de reflexión (E4, paso 1)
 *
 * SIN TRABAJADOR. Aquí solo se encola, se toma, se cierra y se recupera. No
 * hay nada que ejecute un job y eso no es una fase a medias: la cola tiene que
 * ser demostrablemente durable e idempotente ANTES de que algo escriba a
 * partir de ella. Al revés, un fallo de la cola y un fallo del trabajador se
 * confunden y no hay forma de saber cuál duplicó un recuerdo.
 *
 * IDENTIDAD = `perfil/sesion/turno`. Encolar dos veces el mismo turno no crea
 * dos jobs. Es lo que permite que un reinicio recupere trabajo pendiente sin
 * duplicar recuerdos: reencolar es inofensivo por construcción, no porque
 * quien llama se acuerde de comprobarlo.
 *
 * ENTRADA CONGELADA. Un job guarda el mensaje real, la respuesta visible, el
 * marco del turno, la evidencia registrada y el hash del perfil que gobernaba.
 * NO guarda el contrato ni el texto de razonamiento — y no por disciplina de
 * quien llama: es que no existen los campos. El contrato es efímero por
 * diseño, y el razonamiento interno no es lo que se dijo. Reflexionar sobre
 * ellos sería reflexionar sobre algo que nunca ocurrió.
 *
 * El diario de la cola (`hera_cola.jsonl`) es de SOLO AÑADIR y comparte el
 * mismo cerrojo interproceso que el almacén: dos HexOS, o un HexOS y una CLI,
 * no pueden tomar el mismo job.
 */

#ifndef HERA_QUEUE_H
#define HERA_QUEUE_H

#include "hera_store.h"

#define HERA_JOB_ID_MAX     160
#define HERA_JOB_TEXTO_MAX  8192
#define HERA_JOB_INTENTOS   3     /* tras estos, se da por fallido y no vuelve */

typedef enum {
    HERA_JOB_PENDIENTE = 0,
    HERA_JOB_TOMADO,       /* un trabajador lo cogió y aún no ha vuelto */
    HERA_JOB_HECHO,
    HERA_JOB_FALLIDO       /* con motivo; no se reintenta más */
} hera_job_estado_t;

const char *hera_job_estado_nombre(hera_job_estado_t e);

typedef struct {
    char  id[HERA_JOB_ID_MAX];        /* "perfil/sesion/turno" */
    char  perfil[48];
    char  sesion[48];
    unsigned turno;

    /* --- entrada congelada --- */
    char  mensaje[HERA_JOB_TEXTO_MAX];    /* lo que dijo la persona */
    char  respuesta[HERA_JOB_TEXTO_MAX];  /* lo VISIBLE que contestó */
    char  acto[32];                       /* del TurnFrame */
    char  registro[32];
    int   visible_budget, thinking_budget;
    char  evidencia[HERA_ID_MAX];         /* el `dijo` de este turno */
    char  perfil_hash[24];                /* qué perfil gobernaba entonces */

    hera_job_estado_t estado;
    char  dueno[80];      /* "<boot_id>:<pid>" de quien lo tiene tomado */
    int   intentos;
    char  motivo[160];                    /* por qué falló, si falló */
} hera_job_t;

/* Abre la cola del perfil apuntado por HELIOS_HOME y RECUPERA: un job que
 * quedó en TOMADO vuelve a PENDIENTE con un intento más SI su dueño ya no
 * existe. Si sigue vivo, está trabajando y no se toca — devolverlo a la cola
 * sería robárselo, y entonces dos trabajadores reflexionan el mismo turno. Pasados HERA_JOB_INTENTOS se marca FALLIDO y deja de volver —
 * un job que mata a su trabajador no puede quedarse reintentándose para
 * siempre delante de los demás. */
bool hera_cola_abrir(void);
void hera_cola_cerrar(void);
const char *hera_cola_ruta(void);

/* Encola. Idempotente por `id`: si ese turno ya está en la cola (en cualquier
 * estado), no hace nada y devuelve true. Devuelve false solo si el job no cabe
 * o la cola no está abierta — un turno más largo del máximo NO se recorta,
 * porque reflexionar sobre media respuesta es reflexionar sobre otra cosa. */
bool hera_cola_encolar(const hera_job_t *job);

/* Toma el PENDIENTE más antiguo y lo marca TOMADO, todo bajo el mismo cerrojo
 * exclusivo: dos trabajadores no pueden llevarse el mismo. false si no hay. */
bool hera_cola_tomar(hera_job_t *out);

/* Cierra un job. `hecho` guarda cuántas operaciones traía y cuántas eran
 * aceptables — números, nunca el texto. `fallido` guarda el motivo y, si aún
 * quedan intentos, lo devuelve a la cola detrás de los demás. */
bool hera_cola_hecho(const char *id, size_t ops, size_t aceptables);
bool hera_cola_fallido(const char *id, const char *motivo);

size_t hera_cola_pendientes(void);

/* Telemetría: recuentos por estado y nada más. Ni el mensaje, ni la respuesta,
 * ni el motivo si trae texto de la persona dentro. Un resumen que se copia a
 * un log acaba siendo una copia de la memoria en un sitio sin reglas. */
size_t hera_cola_estado_json(char *out, size_t cap);

#endif /* HERA_QUEUE_H */
