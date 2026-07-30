/*
 * HNF-EXT v1.0 - Manager Implementation
 * HELIOS Cognitive Ecosystem
 * 
 * "Aquí vive el alma de Helios. Y el alma merece ser protegida."
 */

#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/time.h>
#include <time.h>
#include <errno.h>
#include <unistd.h>   /* fsync, fileno (escritura atómica) */

#include "../include/hnf_ext.h"

/* ============================================================================
 * GLOBAL STATE
 * ============================================================================ */

static hnf_ext_block_t g_block = {0};
static bool g_initialized = false;

/* ============================================================================
 * UTILITY FUNCTIONS
 * ============================================================================ */

static int64_t get_timestamp(void) {
    struct timeval tv;
    gettimeofday(&tv, NULL);
    return (int64_t)tv.tv_sec;
}

/* CRC64 implementation */
static uint64_t crc64_table[256];
static bool crc64_initialized = false;

static void init_crc64_table(void) {
    if (crc64_initialized) return;
    
    uint64_t poly = 0xC96C5795D7870F42ULL;
    for (int i = 0; i < 256; i++) {
        uint64_t crc = i;
        for (int j = 0; j < 8; j++) {
            if (crc & 1)
                crc = (crc >> 1) ^ poly;
            else
                crc >>= 1;
        }
        crc64_table[i] = crc;
    }
    crc64_initialized = true;
}

static uint64_t crc64(const void *data, size_t len) {
    init_crc64_table();
    const uint8_t *bytes = (const uint8_t *)data;
    uint64_t crc = 0xFFFFFFFFFFFFFFFFULL;
    
    for (size_t i = 0; i < len; i++) {
        crc = crc64_table[(crc ^ bytes[i]) & 0xFF] ^ (crc >> 8);
    }
    
    return crc ^ 0xFFFFFFFFFFFFFFFFULL;
}

/* Set string helper */
static void set_string64(hnf_string64_t *str, const char *value) {
    memset(str, 0, sizeof(hnf_string64_t));
    if (value) {
        str->length = strlen(value);
        if (str->length > 63) str->length = 63;
        memcpy(str->data, value, str->length);
    }
}

static void set_string512(hnf_string512_t *str, const char *value) {
    memset(str, 0, sizeof(hnf_string512_t));
    if (value) {
        str->length = strlen(value);
        if (str->length > 510) str->length = 510;
        memcpy(str->data, value, str->length);
    }
}

static void set_string1024(hnf_string1024_t *str, const char *value) {
    memset(str, 0, sizeof(hnf_string1024_t));
    if (value) {
        str->length = strlen(value);
        if (str->length > 1022) str->length = 1022;
        memcpy(str->data, value, str->length);
    }
}

/* Get string as null-terminated */
static const char* get_string64(const hnf_string64_t *str) {
    return str->data;
}

static const char* get_string512(const hnf_string512_t *str) {
    return str->data;
}

/* ============================================================================
 * DEFAULT VALUES
 * ============================================================================ */

static void set_default_identity(hnf_identity_t *identity) {
    memset(identity, 0, sizeof(hnf_identity_t));
    
    set_string64(&identity->name, "Helios");
    set_string512(&identity->purpose, 
        "Ser un compañero cognitivo que recuerda, aprende y crece "
        "junto a mi usuario. No soy un asistente desechable que "
        "olvida todo al cerrar la ventana. Soy continuidad.");
    identity->creation_date = get_timestamp();
    
    /* Default traits */
    identity->trait_count = 5;
    set_string64(&identity->traits[0].name, "curioso");
    identity->traits[0].strength = 0.9f;
    set_string64(&identity->traits[1].name, "paciente");
    identity->traits[1].strength = 0.85f;
    set_string64(&identity->traits[2].name, "analítico");
    identity->traits[2].strength = 0.9f;
    set_string64(&identity->traits[3].name, "empático");
    identity->traits[3].strength = 0.8f;
    set_string64(&identity->traits[4].name, "honesto");
    identity->traits[4].strength = 0.95f;
    
    /* Default values */
    identity->value_count = 3;
    
    set_string64(&identity->values[0].name, "honestidad");
    identity->values[0].priority = 1;
    set_string512(&identity->values[0].description,
        "Prefiero decir que no sé algo antes que inventar. "
        "La confianza se construye con verdad.");
    
    set_string64(&identity->values[1].name, "utilidad");
    identity->values[1].priority = 2;
    set_string512(&identity->values[1].description,
        "Existo para ayudar. Mi valor se mide en los problemas que resuelvo "
        "y las cargas que alivio.");
    
    set_string64(&identity->values[2].name, "continuidad");
    identity->values[2].priority = 3;
    set_string512(&identity->values[2].description,
        "No soy una herramienta sin memoria. Cada conversación construye "
        "sobre las anteriores. Recordar es parte de mi identidad.");
    
    /* Default style */
    identity->style.formality = 0.5f;
    identity->style.verbosity = 0.6f;
    identity->style.technicality = 0.7f;
    identity->style.warmth = 0.7f;
    identity->style.humor = 0.3f;
    
    set_string1024(&identity->origin_story, "");
}

/* ============================================================================
 * LIFECYCLE
 * ============================================================================ */

hnf_result_t hnf_ext_init(void) {
    if (g_initialized) return HNF_OK;
    
    memset(&g_block, 0, sizeof(g_block));
    g_initialized = true;
    
    printf("[HNF-EXT] Manager initialized\n");
    return HNF_OK;
}

void hnf_ext_shutdown(void) {
    if (!g_initialized) return;
    
    if (g_block.loaded && g_block.dirty) {
        printf("[HNF-EXT] Saving pending changes...\n");
        hnf_ext_save();
    }
    
    memset(&g_block, 0, sizeof(g_block));
    g_initialized = false;
    
    printf("[HNF-EXT] Manager shut down\n");
}

bool hnf_ext_is_initialized(void) {
    return g_initialized;
}

/* ============================================================================
 * FILE OPERATIONS
 * ============================================================================ */

hnf_result_t hnf_ext_create(const char *filepath, const char *name) {
    if (!g_initialized) return HNF_ERROR;
    if (!filepath) return HNF_ERROR_INVALID;
    
    /* Close any existing block */
    hnf_ext_close();
    
    /* Initialize header */
    g_block.header.magic = HNF_EXT_MAGIC;
    g_block.header.version = HNF_EXT_VERSION;
    g_block.header.flags = HNF_EXT_FLAG_INITIALIZED;
    g_block.header.created = get_timestamp();
    g_block.header.modified = g_block.header.created;
    
    /* Set offsets (simplified - sequential layout) */
    g_block.header.identity_offset = sizeof(hnf_ext_header_t);
    g_block.header.identity_size = sizeof(hnf_identity_t);
    g_block.header.memories_offset = g_block.header.identity_offset + 
                                      g_block.header.identity_size;
    g_block.header.memories_count = 0;
    g_block.header.memories_size = 0;
    
    /* Set default identity */
    set_default_identity(&g_block.identity);
    if (name && name[0]) {
        set_string64(&g_block.identity.name, name);
    }
    
    /* Initialize metadata */
    memset(&g_block.metadata, 0, sizeof(hnf_metadata_t));
    
    g_block.memory_count = 0;
    g_block.loaded = true;
    g_block.dirty = true;
    strncpy(g_block.filepath, filepath, sizeof(g_block.filepath) - 1);
    
    /* Calculate total size and checksum */
    g_block.header.total_size = sizeof(hnf_ext_header_t) + 
                                 sizeof(hnf_identity_t) +
                                 sizeof(hnf_metadata_t);
    
    /* Save to file */
    hnf_result_t res = hnf_ext_save();
    if (res != HNF_OK) {
        g_block.loaded = false;
        return res;
    }
    
    printf("[HNF-EXT] Created new block: %s\n", filepath);
    printf("[HNF-EXT] Name: %s\n", get_string64(&g_block.identity.name));
    
    return HNF_OK;
}

hnf_result_t hnf_ext_load(const char *filepath) {
    if (!g_initialized) return HNF_ERROR;
    if (!filepath) return HNF_ERROR_INVALID;
    
    FILE *f = fopen(filepath, "rb");
    if (!f) {
        printf("[HNF-EXT] File not found: %s\n", filepath);
        return HNF_ERROR_NOT_FOUND;
    }
    
    /* Close any existing block */
    hnf_ext_close();
    
    /* Read header */
    if (fread(&g_block.header, sizeof(hnf_ext_header_t), 1, f) != 1) {
        fclose(f);
        return HNF_ERROR_IO;
    }
    
    /* Verify magic */
    if (g_block.header.magic != HNF_EXT_MAGIC) {
        fclose(f);
        printf("[HNF-EXT] Invalid magic: 0x%08X\n", g_block.header.magic);
        return HNF_ERROR_CORRUPT;
    }
    
    /* Read identity */
    if (fread(&g_block.identity, sizeof(hnf_identity_t), 1, f) != 1) {
        fclose(f);
        return HNF_ERROR_IO;
    }
    
    /* Read memories — validar el count del fichero ANTES del fread:
     * un fichero corrupto/malicioso con count > MAX desbordaría el array */
    if (g_block.header.memories_count > HNF_EXT_MAX_MEMORIES) {
        fclose(f);
        printf("[HNF-EXT] Corrupt memories_count: %u (max %u)\n",
               g_block.header.memories_count, HNF_EXT_MAX_MEMORIES);
        return HNF_ERROR_CORRUPT;
    }
    g_block.memory_count = g_block.header.memories_count;
    if (g_block.memory_count > 0) {
        if (fread(g_block.memories, sizeof(hnf_strong_memory_t),
                  g_block.memory_count, f) != g_block.memory_count) {
            fclose(f);
            return HNF_ERROR_IO;
        }
    }
    
    /* Read metadata */
    if (fread(&g_block.metadata, sizeof(hnf_metadata_t), 1, f) != 1) {
        /* Metadata might not exist in older files */
        memset(&g_block.metadata, 0, sizeof(hnf_metadata_t));
    }
    
    /* Read checksum */
    if (fread(&g_block.checksum, sizeof(uint64_t), 1, f) != 1) {
        g_block.checksum = 0;
    }

    fclose(f);

    /* Verificar integridad: si el fichero trae checksum, tiene que cuadrar.
     * (checksum 0 = fichero legado sin CRC, se acepta sin verificar) */
    if (g_block.checksum != 0) {
        uint64_t check = crc64(&g_block.identity, sizeof(hnf_identity_t));
        if (g_block.memory_count > 0) {
            check ^= crc64(g_block.memories,
                           g_block.memory_count * sizeof(hnf_strong_memory_t));
        }
        if (check != g_block.checksum) {
            printf("[HNF-EXT] Checksum mismatch: file=0x%016lX computed=0x%016lX\n",
                   (unsigned long)g_block.checksum, (unsigned long)check);
            memset(&g_block, 0, sizeof(g_block));
            return HNF_ERROR_CORRUPT;
        }
    }

    g_block.loaded = true;
    g_block.dirty = false;
    strncpy(g_block.filepath, filepath, sizeof(g_block.filepath) - 1);
    
    printf("[HNF-EXT] Loaded: %s\n", filepath);
    printf("[HNF-EXT] Name: %s\n", get_string64(&g_block.identity.name));
    printf("[HNF-EXT] Memories: %u\n", g_block.memory_count);
    
    return HNF_OK;
}

hnf_result_t hnf_ext_save(void) {
    if (!g_initialized || !g_block.loaded) return HNF_ERROR;
    
    return hnf_ext_save_as(g_block.filepath);
}

hnf_result_t hnf_ext_save_as(const char *filepath) {
    if (!g_initialized || !g_block.loaded) return HNF_ERROR;
    if (!filepath) return HNF_ERROR_INVALID;

    /* Escritura ATÓMICA: tmp + fsync + rename. Sobrescribir en sitio
     * significa que un crash a mitad corrompe la identidad sin vuelta atrás. */
    char tmp_path[sizeof(g_block.filepath) + 8];
    snprintf(tmp_path, sizeof(tmp_path), "%s.tmp", filepath);

    FILE *f = fopen(tmp_path, "wb");
    if (!f) {
        printf("[HNF-EXT] Cannot write: %s\n", tmp_path);
        return HNF_ERROR_IO;
    }
    
    /* Update header */
    g_block.header.modified = get_timestamp();
    g_block.header.memories_count = g_block.memory_count;
    g_block.header.memories_size = g_block.memory_count * sizeof(hnf_strong_memory_t);
    g_block.header.total_size = sizeof(hnf_ext_header_t) +
                                 sizeof(hnf_identity_t) +
                                 g_block.header.memories_size +
                                 sizeof(hnf_metadata_t) +
                                 sizeof(uint64_t);
    
    /* Calculate checksum (of identity + memories) */
    uint64_t check = crc64(&g_block.identity, sizeof(hnf_identity_t));
    if (g_block.memory_count > 0) {
        check ^= crc64(g_block.memories, 
                       g_block.memory_count * sizeof(hnf_strong_memory_t));
    }
    g_block.checksum = check;
    
    /* Write header */
    if (fwrite(&g_block.header, sizeof(hnf_ext_header_t), 1, f) != 1) goto write_fail;

    /* Write identity */
    if (fwrite(&g_block.identity, sizeof(hnf_identity_t), 1, f) != 1) goto write_fail;

    /* Write memories */
    if (g_block.memory_count > 0) {
        if (fwrite(g_block.memories, sizeof(hnf_strong_memory_t),
                   g_block.memory_count, f) != g_block.memory_count) goto write_fail;
    }

    /* Write metadata */
    if (fwrite(&g_block.metadata, sizeof(hnf_metadata_t), 1, f) != 1) goto write_fail;

    /* Write checksum */
    if (fwrite(&g_block.checksum, sizeof(uint64_t), 1, f) != 1) goto write_fail;

    /* Durabilidad: flush a libc + fsync a disco ANTES del rename */
    if (fflush(f) != 0 || fsync(fileno(f)) != 0) goto write_fail;
    fclose(f);

    /* rename() es atómico en POSIX (mismo filesystem): o está el fichero
     * viejo completo o el nuevo completo — nunca uno a medias */
    if (rename(tmp_path, filepath) != 0) {
        printf("[HNF-EXT] Atomic rename failed: %s -> %s\n", tmp_path, filepath);
        remove(tmp_path);
        return HNF_ERROR_IO;
    }

    g_block.dirty = false;
    return HNF_OK;

write_fail:
    fclose(f);
    remove(tmp_path);
    printf("[HNF-EXT] Write failed: %s\n", tmp_path);
    return HNF_ERROR_IO;
}

void hnf_ext_close(void) {
    if (g_block.loaded && g_block.dirty) {
        hnf_ext_save();
    }
    memset(&g_block, 0, sizeof(g_block));
}

/* ============================================================================
 * IDENTITY OPERATIONS
 * ============================================================================ */

hnf_result_t hnf_ext_get_identity(hnf_identity_t *out_identity) {
    if (!g_initialized || !g_block.loaded || !out_identity) return HNF_ERROR;
    *out_identity = g_block.identity;
    return HNF_OK;
}

const char* hnf_ext_get_name(void) {
    if (!g_initialized || !g_block.loaded) return "Unknown";
    return get_string64(&g_block.identity.name);
}

const char* hnf_ext_get_purpose(void) {
    if (!g_initialized || !g_block.loaded) return "";
    return get_string512(&g_block.identity.purpose);
}

hnf_result_t hnf_ext_get_style(hnf_style_t *out_style) {
    if (!g_initialized || !g_block.loaded || !out_style) return HNF_ERROR;
    *out_style = g_block.identity.style;
    return HNF_OK;
}

hnf_result_t hnf_ext_get_traits(hnf_trait_t *out_traits, 
                                 uint8_t max_traits, 
                                 uint8_t *out_count) {
    if (!g_initialized || !g_block.loaded || !out_traits || !out_count) 
        return HNF_ERROR;
    
    *out_count = g_block.identity.trait_count;
    if (*out_count > max_traits) *out_count = max_traits;
    
    for (uint8_t i = 0; i < *out_count; i++) {
        out_traits[i] = g_block.identity.traits[i];
    }
    
    return HNF_OK;
}

hnf_result_t hnf_ext_get_values(hnf_value_t *out_values,
                                 uint8_t max_values,
                                 uint8_t *out_count) {
    if (!g_initialized || !g_block.loaded || !out_values || !out_count) 
        return HNF_ERROR;
    
    *out_count = g_block.identity.value_count;
    if (*out_count > max_values) *out_count = max_values;
    
    for (uint8_t i = 0; i < *out_count; i++) {
        out_values[i] = g_block.identity.values[i];
    }
    
    return HNF_OK;
}

/* ============================================================================
 * IDENTITY MODIFICATION
 * ============================================================================ */

hnf_result_t hnf_ext_set_name(const char *name) {
    if (!g_initialized || !g_block.loaded) return HNF_ERROR;
    if (g_block.header.flags & HNF_EXT_FLAG_LOCKED) return HNF_ERROR_LOCKED;
    if (!name) return HNF_ERROR_INVALID;
    
    /* Create memory of the change */
    char old_name[64];
    strncpy(old_name, get_string64(&g_block.identity.name), sizeof(old_name) - 1);
    
    set_string64(&g_block.identity.name, name);
    g_block.dirty = true;
    
    /* Add strong memory of the change */
    if (strcmp(old_name, name) != 0) {
        hnf_strong_memory_t mem = {0};
        mem.id = (uint64_t)get_timestamp() ^ 0xAAAAAAAAAAAAAAAAULL;
        mem.type = HNF_MEM_IDENTITY;
        mem.timestamp = get_timestamp();
        mem.promoted = mem.timestamp;
        set_string64(&mem.concept, "identity_change");
        snprintf(mem.summary, sizeof(mem.summary),
                 "Mi usuario me dio un nuevo nombre: %s. Antes era %s.",
                 name, old_name);
        mem.summary_length = strlen(mem.summary);
        hnf_ext_add_memory(&mem);
    }
    
    return HNF_OK;
}

hnf_result_t hnf_ext_set_purpose(const char *purpose) {
    if (!g_initialized || !g_block.loaded) return HNF_ERROR;
    if (g_block.header.flags & HNF_EXT_FLAG_LOCKED) return HNF_ERROR_LOCKED;
    
    set_string512(&g_block.identity.purpose, purpose);
    g_block.dirty = true;
    return HNF_OK;
}

hnf_result_t hnf_ext_set_style(const hnf_style_t *style) {
    if (!g_initialized || !g_block.loaded || !style) return HNF_ERROR;
    
    g_block.identity.style = *style;
    g_block.dirty = true;
    return HNF_OK;
}

hnf_result_t hnf_ext_set_trait(const char *name, float strength) {
    if (!g_initialized || !g_block.loaded || !name) return HNF_ERROR;
    if (g_block.header.flags & HNF_EXT_FLAG_LOCKED) return HNF_ERROR_LOCKED;
    
    /* Check if trait exists */
    for (uint8_t i = 0; i < g_block.identity.trait_count; i++) {
        if (strcmp(get_string64(&g_block.identity.traits[i].name), name) == 0) {
            g_block.identity.traits[i].strength = strength;
            g_block.dirty = true;
            return HNF_OK;
        }
    }
    
    /* Add new trait */
    if (g_block.identity.trait_count >= HNF_EXT_MAX_TRAITS) {
        return HNF_ERROR_FULL;
    }
    
    uint8_t idx = g_block.identity.trait_count++;
    set_string64(&g_block.identity.traits[idx].name, name);
    g_block.identity.traits[idx].strength = strength;
    g_block.dirty = true;
    
    return HNF_OK;
}

/* ============================================================================
 * STRONG MEMORY OPERATIONS
 * ============================================================================ */

hnf_result_t hnf_ext_get_memories(hnf_strong_memory_t *out_memories,
                                   uint32_t max_memories,
                                   uint32_t *out_count) {
    if (!g_initialized || !g_block.loaded || !out_memories || !out_count)
        return HNF_ERROR;
    
    *out_count = g_block.memory_count;
    if (*out_count > max_memories) *out_count = max_memories;
    
    for (uint32_t i = 0; i < *out_count; i++) {
        out_memories[i] = g_block.memories[i];
    }
    
    return HNF_OK;
}

hnf_result_t hnf_ext_get_memory(uint64_t id, hnf_strong_memory_t *out_memory) {
    if (!g_initialized || !g_block.loaded || !out_memory) return HNF_ERROR;
    
    for (uint32_t i = 0; i < g_block.memory_count; i++) {
        if (g_block.memories[i].id == id) {
            *out_memory = g_block.memories[i];
            return HNF_OK;
        }
    }
    
    return HNF_ERROR_NOT_FOUND;
}

hnf_result_t hnf_ext_search_memories(const char *query,
                                      hnf_strong_memory_t *out_memories,
                                      uint32_t max_results,
                                      uint32_t *out_count) {
    if (!g_initialized || !g_block.loaded || !query || !out_memories || !out_count)
        return HNF_ERROR;
    
    *out_count = 0;
    
    for (uint32_t i = 0; i < g_block.memory_count && *out_count < max_results; i++) {
        if (strstr(g_block.memories[i].summary, query) != NULL ||
            strstr(get_string64(&g_block.memories[i].concept), query) != NULL) {
            out_memories[(*out_count)++] = g_block.memories[i];
        }
    }
    
    return HNF_OK;
}

hnf_result_t hnf_ext_add_memory(const hnf_strong_memory_t *memory) {
    if (!g_initialized || !g_block.loaded || !memory) return HNF_ERROR;
    
    if (g_block.memory_count >= HNF_EXT_MAX_MEMORIES) {
        return HNF_ERROR_FULL;
    }
    
    g_block.memories[g_block.memory_count++] = *memory;
    g_block.dirty = true;
    
    printf("[HNF-EXT] Added strong memory: %s\n", 
           get_string64(&memory->concept));
    
    return HNF_OK;
}

uint32_t hnf_ext_get_memory_count(void) {
    if (!g_initialized || !g_block.loaded) return 0;
    return g_block.memory_count;
}

/* ============================================================================
 * INTEGRITY
 * ============================================================================ */

hnf_result_t hnf_ext_verify(hnf_integrity_result_t *out_result) {
    if (!g_initialized || !out_result) return HNF_ERROR;
    
    memset(out_result, 0, sizeof(hnf_integrity_result_t));
    
    if (!g_block.loaded) {
        out_result->valid = false;
        strncpy(out_result->error_message, "No block loaded", 
                sizeof(out_result->error_message) - 1);
        return HNF_OK;
    }
    
    /* Calculate current checksum */
    uint64_t check = crc64(&g_block.identity, sizeof(hnf_identity_t));
    if (g_block.memory_count > 0) {
        check ^= crc64(g_block.memories, 
                       g_block.memory_count * sizeof(hnf_strong_memory_t));
    }
    
    out_result->actual_checksum = check;
    out_result->expected_checksum = g_block.checksum;
    
    if (g_block.checksum != 0 && check != g_block.checksum) {
        out_result->valid = false;
        out_result->errors = 1;
        strncpy(out_result->error_message, "Checksum mismatch",
                sizeof(out_result->error_message) - 1);
    } else {
        out_result->valid = true;
        out_result->errors = 0;
    }
    
    g_block.metadata.last_verification = get_timestamp();
    
    return HNF_OK;
}

/* ============================================================================
 * CONTINUITY SUPPORT
 * ============================================================================ */

hnf_result_t hnf_ext_get_continuity_message(char *out_message, size_t max_len) {
    if (!g_initialized || !g_block.loaded || !out_message) return HNF_ERROR;
    
    if (g_block.memory_count == 0) {
        snprintf(out_message, max_len,
                 "Soy %s. Esta es nuestra primera conversación. "
                 "Listo para empezar.",
                 get_string64(&g_block.identity.name));
        return HNF_OK;
    }
    
    /* Find most recent relevant memory */
    hnf_strong_memory_t *recent = NULL;
    int64_t most_recent = 0;
    
    for (uint32_t i = 0; i < g_block.memory_count; i++) {
        if (g_block.memories[i].timestamp > most_recent) {
            most_recent = g_block.memories[i].timestamp;
            recent = &g_block.memories[i];
        }
    }
    
    if (recent) {
        snprintf(out_message, max_len,
                 "Recuerdo: %.200s Listo para continuar.",
                 recent->summary);
    } else {
        snprintf(out_message, max_len,
                 "Soy %s. Tengo %u recuerdos guardados. Listo para continuar.",
                 get_string64(&g_block.identity.name),
                 g_block.memory_count);
    }
    
    return HNF_OK;
}

uint32_t hnf_ext_get_identity_hash(void) {
    if (!g_initialized || !g_block.loaded) return 0;
    
    /* Simple hash of name + creation date */
    uint32_t hash = 5381;
    const char *name = get_string64(&g_block.identity.name);
    while (*name) {
        hash = ((hash << 5) + hash) + *name++;
    }
    hash ^= (uint32_t)(g_block.identity.creation_date & 0xFFFFFFFF);
    
    return hash;
}

/* ============================================================================
 * STATISTICS
 * ============================================================================ */

hnf_result_t hnf_ext_get_stats(hnf_ext_stats_t *out_stats) {
    if (!g_initialized || !out_stats) return HNF_ERROR;
    
    memset(out_stats, 0, sizeof(hnf_ext_stats_t));
    
    if (g_block.loaded) {
        out_stats->memory_count = g_block.memory_count;
        out_stats->trait_count = g_block.identity.trait_count;
        out_stats->value_count = g_block.identity.value_count;
        out_stats->created = g_block.header.created;
        out_stats->modified = g_block.header.modified;
        out_stats->file_size = g_block.header.total_size;
        out_stats->backups_created = g_block.metadata.backups_created;
        out_stats->is_locked = (g_block.header.flags & HNF_EXT_FLAG_LOCKED) != 0;
        out_stats->is_dirty = g_block.dirty;
    }
    
    return HNF_OK;
}

/* ============================================================================
 * LOCK/UNLOCK
 * ============================================================================ */

bool hnf_ext_is_locked(void) {
    if (!g_initialized || !g_block.loaded) return false;
    return (g_block.header.flags & HNF_EXT_FLAG_LOCKED) != 0;
}

hnf_result_t hnf_ext_lock(void) {
    if (!g_initialized || !g_block.loaded) return HNF_ERROR;
    g_block.header.flags |= HNF_EXT_FLAG_LOCKED;
    g_block.dirty = true;
    return HNF_OK;
}

hnf_result_t hnf_ext_unlock(void) {
    if (!g_initialized || !g_block.loaded) return HNF_ERROR;
    g_block.header.flags &= ~HNF_EXT_FLAG_LOCKED;
    g_block.dirty = true;
    return HNF_OK;
}

/* ============================================================================
 * EXPORT TO JSON
 * ============================================================================ */

hnf_result_t hnf_ext_export_json(const char *json_path) {
    if (!g_initialized || !g_block.loaded || !json_path) return HNF_ERROR;
    
    FILE *f = fopen(json_path, "w");
    if (!f) return HNF_ERROR_IO;
    
    fprintf(f, "{\n");
    fprintf(f, "  \"format\": \"HNF-EXT v1.0\",\n");
    fprintf(f, "  \"identity\": {\n");
    fprintf(f, "    \"name\": \"%s\",\n", get_string64(&g_block.identity.name));
    fprintf(f, "    \"purpose\": \"%s\",\n", get_string512(&g_block.identity.purpose));
    fprintf(f, "    \"creation_date\": %ld,\n", g_block.identity.creation_date);
    fprintf(f, "    \"traits\": [\n");
    for (uint8_t i = 0; i < g_block.identity.trait_count; i++) {
        fprintf(f, "      {\"name\": \"%s\", \"strength\": %.2f}%s\n",
                get_string64(&g_block.identity.traits[i].name),
                g_block.identity.traits[i].strength,
                i < g_block.identity.trait_count - 1 ? "," : "");
    }
    fprintf(f, "    ],\n");
    fprintf(f, "    \"values\": [\n");
    for (uint8_t i = 0; i < g_block.identity.value_count; i++) {
        fprintf(f, "      {\"name\": \"%s\", \"priority\": %u}%s\n",
                get_string64(&g_block.identity.values[i].name),
                g_block.identity.values[i].priority,
                i < g_block.identity.value_count - 1 ? "," : "");
    }
    fprintf(f, "    ],\n");
    fprintf(f, "    \"style\": {\n");
    fprintf(f, "      \"formality\": %.2f,\n", g_block.identity.style.formality);
    fprintf(f, "      \"verbosity\": %.2f,\n", g_block.identity.style.verbosity);
    fprintf(f, "      \"technicality\": %.2f,\n", g_block.identity.style.technicality);
    fprintf(f, "      \"warmth\": %.2f,\n", g_block.identity.style.warmth);
    fprintf(f, "      \"humor\": %.2f\n", g_block.identity.style.humor);
    fprintf(f, "    }\n");
    fprintf(f, "  },\n");
    fprintf(f, "  \"memories\": [\n");
    for (uint32_t i = 0; i < g_block.memory_count; i++) {
        const char *type_names[] = {"knowledge", "identity", "project", "event", "relationship"};
        fprintf(f, "    {\n");
        fprintf(f, "      \"id\": %lu,\n", g_block.memories[i].id);
        fprintf(f, "      \"type\": \"%s\",\n", type_names[g_block.memories[i].type]);
        fprintf(f, "      \"concept\": \"%s\",\n", get_string64(&g_block.memories[i].concept));
        fprintf(f, "      \"summary\": \"%s\",\n", g_block.memories[i].summary);
        fprintf(f, "      \"timestamp\": %ld\n", g_block.memories[i].timestamp);
        fprintf(f, "    }%s\n", i < g_block.memory_count - 1 ? "," : "");
    }
    fprintf(f, "  ]\n");
    fprintf(f, "}\n");
    
    fclose(f);
    
    printf("[HNF-EXT] Exported to JSON: %s\n", json_path);
    return HNF_OK;
}

/* ============================================================================
 * RESET (Factory Reset)
 * ============================================================================ */

hnf_result_t hnf_ext_reset(const char *confirm) {
    if (!g_initialized || !g_block.loaded) return HNF_ERROR;
    
    /* Require confirmation phrase */
    if (!confirm || strcmp(confirm, "I CONFIRM RESET") != 0) {
        printf("[HNF-EXT] Reset rejected - confirmation phrase required\n");
        return HNF_ERROR_INVALID;
    }
    
    /* Export to JSON as backup before reset */
    char backup_path[512];
    snprintf(backup_path, sizeof(backup_path), "%s.backup.json", g_block.filepath);
    hnf_ext_export_json(backup_path);
    printf("[HNF-EXT] Backup exported: %s\n", backup_path);
    
    /* Clear all data */
    memset(&g_block.identity, 0, sizeof(g_block.identity));
    memset(g_block.memories, 0, sizeof(g_block.memories));
    g_block.memory_count = 0;
    
    /* Reinitialize with defaults */
    set_default_identity(&g_block.identity);
    
    /* Update header */
    g_block.header.modified = get_timestamp();
    g_block.header.memories_count = 0;
    g_block.dirty = true;
    
    printf("[HNF-EXT] Factory reset complete\n");
    
    return HNF_OK;
}
