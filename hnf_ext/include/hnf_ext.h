/*
 * HNF-EXT v1.0 - Manager API
 * HELIOS Cognitive Ecosystem
 * 
 * "Sin este bloque, Helios es solo un LLM con contexto.
 *  Con este bloque, Helios es Helios."
 * 
 * Este módulo gestiona el bloque HNF-EXT que contiene:
 *   - IdentityCore: quién es Helios
 *   - StrongMemories: recuerdos permanentes
 *   - Metadata: información de mantenimiento
 * 
 * IMPORTANTE: Solo HERA puede escribir en HNF-EXT.
 * Memory Core prepara candidatos, HERA aprueba.
 */

#ifndef HNF_EXT_H
#define HNF_EXT_H

#include "hnf_ext_types.h"

/* ============================================================================
 * LIFECYCLE
 * ============================================================================ */

/*
 * Initialize HNF-EXT Manager
 * 
 * @return HNF_OK on success
 */
hnf_result_t hnf_ext_init(void);

/*
 * Shutdown HNF-EXT Manager
 * Saves any pending changes
 */
void hnf_ext_shutdown(void);

/*
 * Check if manager is initialized
 */
bool hnf_ext_is_initialized(void);

/* ============================================================================
 * FILE OPERATIONS
 * ============================================================================ */

/*
 * Create a new HNF-EXT block with default values
 * 
 * @param filepath Path to create the file
 * @param name Initial name for Helios
 * @return HNF_OK on success
 */
hnf_result_t hnf_ext_create(const char *filepath, const char *name);

/*
 * Load an existing HNF-EXT block
 * 
 * @param filepath Path to the file
 * @return HNF_OK on success
 */
hnf_result_t hnf_ext_load(const char *filepath);

/*
 * Save current state to file
 * 
 * @return HNF_OK on success
 */
hnf_result_t hnf_ext_save(void);

/*
 * Save to a specific path (backup/export)
 */
hnf_result_t hnf_ext_save_as(const char *filepath);

/*
 * Close current block without saving
 */
void hnf_ext_close(void);

/* ============================================================================
 * IDENTITY OPERATIONS (read-only for most modules)
 * ============================================================================ */

/*
 * Get the complete identity
 * 
 * @param out_identity Output buffer
 * @return HNF_OK on success
 */
hnf_result_t hnf_ext_get_identity(hnf_identity_t *out_identity);

/*
 * Get Helios name
 */
const char* hnf_ext_get_name(void);

/*
 * Get Helios purpose
 */
const char* hnf_ext_get_purpose(void);

/*
 * Get style profile
 */
hnf_result_t hnf_ext_get_style(hnf_style_t *out_style);

/*
 * Get traits
 * 
 * @param out_traits Output array
 * @param max_traits Maximum to retrieve
 * @param out_count Actual count
 */
hnf_result_t hnf_ext_get_traits(hnf_trait_t *out_traits, 
                                 uint8_t max_traits, 
                                 uint8_t *out_count);

/*
 * Get values
 */
hnf_result_t hnf_ext_get_values(hnf_value_t *out_values,
                                 uint8_t max_values,
                                 uint8_t *out_count);

/* ============================================================================
 * IDENTITY MODIFICATION (HERA only)
 * ============================================================================ */

/*
 * Update Helios name
 * Creates a strong memory of the change
 * 
 * @param name New name
 * @return HNF_OK on success
 */
hnf_result_t hnf_ext_set_name(const char *name);

/*
 * Update purpose
 */
hnf_result_t hnf_ext_set_purpose(const char *purpose);

/*
 * Update style profile
 */
hnf_result_t hnf_ext_set_style(const hnf_style_t *style);

/*
 * Add or update a trait
 */
hnf_result_t hnf_ext_set_trait(const char *name, float strength);

/*
 * Remove a trait
 */
hnf_result_t hnf_ext_remove_trait(const char *name);

/*
 * Add or update a value
 */
hnf_result_t hnf_ext_set_value(const char *name, uint8_t priority, 
                                const char *description);

/*
 * Remove a value
 */
hnf_result_t hnf_ext_remove_value(const char *name);

/* ============================================================================
 * STRONG MEMORY OPERATIONS
 * ============================================================================ */

/*
 * Get all strong memories
 * 
 * @param out_memories Output array
 * @param max_memories Maximum to retrieve
 * @param out_count Actual count
 */
hnf_result_t hnf_ext_get_memories(hnf_strong_memory_t *out_memories,
                                   uint32_t max_memories,
                                   uint32_t *out_count);

/*
 * Get a specific memory by ID
 */
hnf_result_t hnf_ext_get_memory(uint64_t id, hnf_strong_memory_t *out_memory);

/*
 * Search memories by text
 * 
 * @param query Search query
 * @param out_memories Output array
 * @param max_results Maximum results
 * @param out_count Actual count
 */
hnf_result_t hnf_ext_search_memories(const char *query,
                                      hnf_strong_memory_t *out_memories,
                                      uint32_t max_results,
                                      uint32_t *out_count);

/*
 * Add a new strong memory (HERA only)
 * This is called after HERA approves a candidate from Memory Core
 * 
 * @param memory Memory to add
 * @return HNF_OK on success
 */
hnf_result_t hnf_ext_add_memory(const hnf_strong_memory_t *memory);

/*
 * Mark memory for deletion (soft delete)
 * Actual deletion after 7 days
 */
hnf_result_t hnf_ext_mark_deleted(uint64_t id);

/*
 * Get memory count
 */
uint32_t hnf_ext_get_memory_count(void);

/* ============================================================================
 * INTEGRITY AND MAINTENANCE
 * ============================================================================ */

/*
 * Verify block integrity
 * 
 * @param out_result Integrity check result
 */
hnf_result_t hnf_ext_verify(hnf_integrity_result_t *out_result);

/*
 * Create backup
 * 
 * @param backup_path Path for backup (NULL for auto-generated)
 * @param out_path Output: actual backup path
 */
hnf_result_t hnf_ext_backup(const char *backup_path, char *out_path, size_t out_len);

/*
 * Restore from backup
 */
hnf_result_t hnf_ext_restore(const char *backup_path);

/*
 * Export to JSON (human-readable)
 * 
 * @param json_path Output JSON path
 */
hnf_result_t hnf_ext_export_json(const char *json_path);

/*
 * Import from JSON
 */
hnf_result_t hnf_ext_import_json(const char *json_path);

/* ============================================================================
 * SPECIAL OPERATIONS
 * ============================================================================ */

/*
 * Lock identity (prevent modifications)
 */
hnf_result_t hnf_ext_lock(void);

/*
 * Unlock identity
 */
hnf_result_t hnf_ext_unlock(void);

/*
 * Check if locked
 */
bool hnf_ext_is_locked(void);

/*
 * Full reset (creates backup first)
 * WARNING: This "kills" the current Helios
 * 
 * @param confirm Must be "I CONFIRM RESET"
 */
hnf_result_t hnf_ext_reset(const char *confirm);

/* ============================================================================
 * CONTINUITY SUPPORT
 * ============================================================================ */

/*
 * Get continuity message for boot
 * Generates a message based on recent strong memories
 * 
 * @param out_message Output buffer
 * @param max_len Buffer size
 */
hnf_result_t hnf_ext_get_continuity_message(char *out_message, size_t max_len);

/*
 * Get identity hash (for quick identity verification)
 */
uint32_t hnf_ext_get_identity_hash(void);

/* ============================================================================
 * STATISTICS
 * ============================================================================ */

typedef struct {
    uint32_t memory_count;
    uint32_t trait_count;
    uint32_t value_count;
    int64_t  created;
    int64_t  modified;
    uint64_t file_size;
    uint32_t backups_created;
    bool     is_locked;
    bool     is_dirty;
} hnf_ext_stats_t;

hnf_result_t hnf_ext_get_stats(hnf_ext_stats_t *out_stats);

#endif /* HNF_EXT_H */
