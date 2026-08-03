/*
 * HEXOS — registro durable de chats
 *
 * Héctor ofrece sesiones genéricas y las pierde al morir. HexOS es quien sabe
 * que una sesión es "el chat del libro", quien conserva lo hablado y quien
 * puede reconstruirlo mañana. Esa es la frontera: el motor no recuerda nada
 * entre arranques y no tiene por qué.
 *
 * UN SOLO DUEÑO. No hay cuentas ni usuarios: los chats viven en el perfil
 * (HELIOS_HOME) y ese perfil es de una persona. Meter identidades aquí ahora
 * sería inventarse un problema que no existe.
 *
 * TRES ESTADOS QUE NO SON EL MISMO, y confundirlos es el fallo entero:
 *
 *   · ACTIVO      — el chat que se está mirando. Solo uno.
 *   · SESIÓN VIVA — Héctor tiene su KV cargado. Cambiar de chat NO la mata:
 *                   el anterior queda pausado, con su caché intacto, y volver
 *                   a él sigue la conversación en vez de rehacerla.
 *   · EXISTE      — está en el registro con su transcripción. Sobrevive a que
 *                   se cierre la sesión, a que muera Héctor y a reiniciar.
 *
 * Cerrar libera el KV y conserva el chat. Borrar es otra cosa, y hay que
 * pedirla aparte.
 *
 * El diario (`chats.jsonl`) es de SOLO AÑADIR y con el mismo cerrojo que el
 * resto: HexOS puede no ser el único proceso que lo mire.
 */

#ifndef HEXOS_CHATS_H
#define HEXOS_CHATS_H

#include <stdbool.h>
#include <stddef.h>

#define CHAT_ID_MAX      32
#define CHAT_TITULO_MAX  128
#define CHAT_LINEAS_MAX  256      /* turnos guardados por chat */
#define CHAT_TEXTO_MAX   8192
#define CHATS_MAX        64

typedef struct {
    char rol[16];                 /* "user" | "assistant" */
    char *texto;
    /* La respuesta se cortó al cambiar de chat. Se guarda igual y se marca:
     * enseñarla como si estuviera entera sería mentir sobre lo que dijo. */
    bool detenido;
} chat_linea_t;

typedef struct {
    char   id[CHAT_ID_MAX];
    char   titulo[CHAT_TITULO_MAX];
    long long creado, actualizado;
    bool   borrado;

    /* Transcripción canónica: solo lo que se dijo. Ni perfil ni contrato —
     * son efímeros, y guardarlos aquí los volvería permanentes por la puerta
     * de atrás. Es lo que permite reconstruir el KV desde cero. */
    chat_linea_t lineas[CHAT_LINEAS_MAX];
    size_t lineas_n;

    /* Estado VOLÁTIL: si Héctor tiene ahora mismo el KV de este chat. No se
     * guarda en el diario a propósito — al arrancar es falso para todos,
     * porque el motor acaba de nacer y no tiene ninguna sesión. Persistirlo
     * sería prometer un KV que no existe. */
    bool sesion_viva;
} chat_t;

bool chats_abrir(void);
void chats_cerrar(void);

/* Crea un chat y devuelve su id por `out_id`. El título puede venir vacío. */
bool chats_crear(const char *titulo, char *out_id, size_t cap);

/* Lista los no borrados, del más reciente al más viejo. */
size_t chats_listar(const chat_t **out, size_t cap);
const chat_t *chats_buscar(const char *id);

/* Activo: solo uno. Activar otro NO cierra el anterior — queda pausado con su
 * KV vivo, que es justo lo que hace que volver sea barato. */
bool chats_activar(const char *id);
const char *chats_activo(void);

/* Anota lo dicho. `actualizado` avanza, que es lo que ordena la lista. */
bool chats_anotar(const char *id, const char *rol, const char *texto);
bool chats_anotar_estado(const char *id, const char *rol, const char *texto,
                         bool detenido);

/* Renombrar a mano, desde el menú del chat. */
bool chats_renombrar(const char *id, const char *titulo);

/* Título automático: primera línea del primer mensaje, recortada. NO gasta
 * inferencia — pedirle un título al modelo cuesta un turno y una espera, y
 * para una etiqueta de barra lateral no compensa. No pisa un título puesto
 * a mano. */
bool chats_titular_por_mensaje(const char *id, const char *mensaje);

/* Marca si Héctor tiene el KV de este chat cargado ahora mismo. */
void chats_marcar_sesion(const char *id, bool viva);
bool chats_sesion_viva(const char *id);

/* Cierra la sesión: libera el KV en Héctor y CONSERVA la conversación. */
bool chats_cerrar_sesion(const char *id);

/* Borra el chat. Operación distinta y explícita: cerrar no borra. */
bool chats_borrar(const char *id);

/* JSON de la lista para la API. Incluye el estado de sesión y cuántos turnos
 * lleva, pero NO la transcripción entera: una lista no es un volcado. */
size_t chats_listar_json(char *out, size_t cap);

/* JSON de un chat con su transcripción, para pintarlo al abrirlo. */
size_t chats_json(const char *id, char *out, size_t cap);

#endif /* HEXOS_CHATS_H */
