/*
 * MEMORY CORE v3.0 - Main API
 * HELIOS Cognitive Ecosystem
 * 
 * Memory Core es el SUBSISTEMA DE ALMACENAMIENTO de memoria de Helios.
 * 
 * Su misión es:
 *   • Almacenar eventos, conceptos y estados
 *   • Indexar y organizar la memoria
 *   • Ejecutar búsquedas semánticas
 *   • Mover datos entre niveles (RAM ↔ Disco)
 *   • Preparar candidatos de memoria esencial
 *   • Mantener coherencia de datos
 * 
 * Memory Core NO decide:
 *   • Qué recuerdos son importantes → Eso es HERA
 *   • Qué se promueve o degrada → Eso es HERA
 *   • Qué entra en HNF-EXT → Eso es HERA
 *   • Límites de recursos → Eso es HEXOS (vía HERA)
 */

#ifndef MEMORY_CORE_H
#define MEMORY_CORE_H

#include "mc_types.h"

/* ============================================================================
 * LIFECYCLE
 * ============================================================================ */

/*
 * Initialize Memory Core
 * 
 * @param config Configuration (NULL for defaults)
 * @return MC_OK on success
 */
mc_result_t mc_init(const mc_config_t *config);

/*
 * Shutdown Memory Core
 * Flushes pending data and releases resources
 */
void mc_shutdown(void);

/*
 * Check if Memory Core is initialized
 */
bool mc_is_initialized(void);

/* ============================================================================
 * HEXOS IPC CONNECTION
 * ============================================================================ */

/*
 * Connect to HEXOS IPC Bus
 * Memory Core will update its state in shared memory
 * 
 * @return MC_OK on success
 */
mc_result_t mc_connect_hexos(void);

/*
 * Disconnect from HEXOS IPC Bus
 */
void mc_disconnect_hexos(void);

/* ============================================================================
 * EPISODIC STORE
 * ============================================================================ */

/*
 * Store an episodic event (what happened)
 * 
 * @param event Event to store
 * @param out_id Output: assigned ID
 * @return MC_OK on success
 */
mc_result_t mc_store_episodic(const mc_episodic_event_t *event, uint64_t *out_id);

/*
 * Retrieve an episodic event by ID
 * 
 * @param id Event ID
 * @param out_event Output: event data
 * @return MC_OK on success, MC_ERROR_NOT_FOUND if not found
 */
mc_result_t mc_get_episodic(uint64_t id, mc_episodic_event_t *out_event);

/*
 * Get recent episodic events
 * 
 * @param count Maximum number to retrieve
 * @param out_events Output array (caller allocates)
 * @param out_count Output: actual count retrieved
 * @return MC_OK on success
 */
mc_result_t mc_get_recent_episodic(uint32_t count, 
                                    mc_episodic_event_t *out_events, 
                                    uint32_t *out_count);

/* ============================================================================
 * SEMANTIC STORE
 * ============================================================================ */

/*
 * Store or update a semantic concept
 * 
 * @param concept Concept to store
 * @param out_id Output: assigned ID
 * @return MC_OK on success
 */
mc_result_t mc_store_concept(const mc_concept_t *concept, uint64_t *out_id);

/*
 * Retrieve a concept by ID
 */
mc_result_t mc_get_concept(uint64_t id, mc_concept_t *out_concept);

/*
 * Find concept by name
 */
mc_result_t mc_find_concept(const char *name, mc_concept_t *out_concept);

/*
 * Store a relation between concepts
 */
mc_result_t mc_store_relation(const mc_relation_t *relation);

/*
 * Get relations for a concept
 * 
 * @param concept_id Concept ID
 * @param out_relations Output array
 * @param max_relations Maximum to retrieve
 * @param out_count Actual count
 */
mc_result_t mc_get_relations(uint64_t concept_id,
                              mc_relation_t *out_relations,
                              uint32_t max_relations,
                              uint32_t *out_count);

/* ============================================================================
 * EMBEDDINGS
 * ============================================================================ */

/*
 * Store an embedding vector
 * 
 * @param embedding Embedding to store (vector must be allocated)
 * @param out_id Output: assigned ID
 */
mc_result_t mc_store_embedding(const mc_embedding_t *embedding, uint64_t *out_id);

/*
 * Retrieve an embedding by ID
 * Note: caller must free out_embedding->vector
 */
mc_result_t mc_get_embedding(uint64_t id, mc_embedding_t *out_embedding);

/*
 * Find similar embeddings (nearest neighbors)
 * 
 * @param query_vector Query vector
 * @param dimension Vector dimension
 * @param max_results Maximum results
 * @param out_ids Output: IDs of similar items
 * @param out_scores Output: similarity scores
 * @param out_count Actual count
 */
mc_result_t mc_find_similar(const float *query_vector,
                             uint16_t dimension,
                             uint32_t max_results,
                             uint64_t *out_ids,
                             float *out_scores,
                             uint32_t *out_count);

/* ============================================================================
 * UNIFIED QUERY ENGINE
 * ============================================================================ */

/*
 * Execute a query across all stores
 * 
 * @param query Query parameters
 * @param result Output: query results (caller must call mc_free_query_result)
 * @return MC_OK on success
 */
mc_result_t mc_query(const mc_query_t *query, mc_query_result_t *result);

/*
 * Free query results
 */
void mc_free_query_result(mc_query_result_t *result);

/* ============================================================================
 * INDEX OPERATIONS
 * ============================================================================ */

/*
 * Get a memory item from the index
 */
mc_result_t mc_index_get(uint64_t id, mc_item_t *out_item);

/*
 * Update item access (increments access_count, updates last_access)
 */
mc_result_t mc_index_touch(uint64_t id);

/*
 * Mark item as candidate for HNF-EXT
 */
mc_result_t mc_index_mark_candidate(uint64_t id);

/*
 * Get all candidates pending for HNF-EXT
 */
mc_result_t mc_get_candidates(mc_item_t *out_items, 
                               uint32_t max_items, 
                               uint32_t *out_count);

/* ============================================================================
 * ARCHIVAL OPERATIONS
 * ============================================================================ */

/*
 * Archive current day's data to disk
 * Called automatically if auto_archive is enabled, or manually by HERA
 */
mc_result_t mc_archive_day(void);

/*
 * Load archived data from a specific date
 * 
 * @param year Year (e.g., 2026)
 * @param month Month (1-12)
 * @param day Day (1-31)
 */
mc_result_t mc_load_archive(int year, int month, int day);

/*
 * Get list of archived dates
 */
mc_result_t mc_list_archives(int *out_years, int *out_months, int *out_days,
                              uint32_t max_count, uint32_t *out_count);

/* ============================================================================
 * CHECKPOINT OPERATIONS (for HEXOS continuity)
 * ============================================================================ */

/*
 * Prepare a checkpoint for HEXOS continuity protocol
 * 
 * @param out_checkpoint Output checkpoint (caller must call mc_free_checkpoint)
 */
mc_result_t mc_prepare_checkpoint(mc_checkpoint_t *out_checkpoint);

/*
 * Restore from a checkpoint
 */
mc_result_t mc_restore_checkpoint(const mc_checkpoint_t *checkpoint);

/*
 * Free checkpoint resources
 */
void mc_free_checkpoint(mc_checkpoint_t *checkpoint);

/* ============================================================================
 * HNF-EXT CANDIDATE PREPARATION
 * ============================================================================ */

/*
 * Prepare a core memory proposal for HERA
 * Memory Core identifies high-relevance items, but HERA decides
 * 
 * @param item_id Item to evaluate
 * @param out_proposal Output proposal
 */
mc_result_t mc_prepare_proposal(uint64_t item_id, mc_core_proposal_t *out_proposal);

/*
 * Mark item as promoted to HNF-EXT (reference only, data stays in HNF-EXT)
 */
mc_result_t mc_mark_essential(uint64_t item_id);

/* ============================================================================
 * STATISTICS AND MONITORING
 * ============================================================================ */

/*
 * Get current statistics
 */
mc_result_t mc_get_stats(mc_stats_t *out_stats);

/*
 * Get current pressure level
 */
mc_pressure_t mc_get_pressure(void);

/*
 * Verify integrity of all data
 * 
 * @param repair If true, attempt to repair issues
 * @param out_errors Output: number of errors found
 */
mc_result_t mc_verify_integrity(bool repair, uint32_t *out_errors);

/* ============================================================================
 * DEGRADATION (called by HERA when under pressure)
 * ============================================================================ */

/*
 * Degrade least relevant items from RAM to disk
 * 
 * @param target_mb Target size reduction in MB
 * @param out_degraded Output: items actually degraded
 */
mc_result_t mc_degrade(uint64_t target_mb, uint32_t *out_degraded);

/* ============================================================================
 * UTILITY
 * ============================================================================ */

/*
 * Generate a unique ID for a memory item
 */
uint64_t mc_generate_id(const void *content, size_t size);

/*
 * Get current timestamp
 */
int64_t mc_timestamp(void);

/*
 * Format timestamp to string
 */
void mc_format_timestamp(int64_t ts, char *buf, size_t len);

#endif /* MEMORY_CORE_H */
