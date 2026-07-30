/*
 * HERA v3.0 - Main API
 * HELIOS Cognitive Ecosystem
 * 
 * HERA es la CAPA COGNITIVA de Helios.
 * 
 * Su misión es:
 *   • Gobernar la memoria jerárquica (HHMS)
 *   • Mantener la identidad persistente
 *   • Preservar la continuidad semántica entre sesiones
 *   • Coordinar con HEXOS para checkpoints y recuperación
 *   • Decidir qué recuerdos son esenciales
 */

#ifndef HERA_H
#define HERA_H

#include "hera_types.h"

/* ============================================================================
 * LIFECYCLE
 * ============================================================================ */

/*
 * Initialize HERA
 * 
 * @param config Configuration (NULL for defaults)
 * @return HERA_OK on success
 */
hera_result_t hera_init(const hera_config_t *config);

/*
 * Shutdown HERA
 * Performs final consolidation if needed
 */
void hera_shutdown(void);

/*
 * Check if HERA is initialized
 */
bool hera_is_initialized(void);

/*
 * Get current state
 */
hera_state_t hera_get_state(void);

/* ============================================================================
 * HEXOS INTERFACE (signals from HEXOS)
 * ============================================================================ */

/*
 * Handle signal from HEXOS
 * 
 * @param signal Signal type
 * @param pressure Pressure level (for MEMORY_PRESSURE signal)
 * @return HERA_OK on success
 */
hera_result_t hera_handle_hexos_signal(hexos_signal_t signal, 
                                        hera_pressure_t pressure);

/*
 * Connect to HEXOS IPC
 */
hera_result_t hera_connect_hexos(void);

/*
 * Disconnect from HEXOS IPC
 */
void hera_disconnect_hexos(void);

/* ============================================================================
 * COGNITIVE KERNEL INTERFACE
 * ============================================================================ */

/*
 * Handle event from Cognitive Kernel
 * 
 * @param event Event type
 * @param data Event-specific data (cast based on event type)
 * @return Response code
 */
hera_response_t hera_handle_ck_event(ck_event_type_t event, void *data);

/*
 * Query memories for Cognitive Kernel
 * 
 * @param query Query parameters
 * @param out_ids Output: array of memory IDs
 * @param max_ids Maximum IDs to return
 * @param out_count Output: actual count
 * @return HERA_OK on success
 */
hera_result_t hera_query_memories(const hera_memory_query_t *query,
                                   uint64_t *out_ids,
                                   uint32_t max_ids,
                                   uint32_t *out_count);

/*
 * Submit core memory proposal from CK
 * 
 * @param proposal Proposal to evaluate
 * @return Response: ACCEPTED, REJECTED, or PENDING
 */
hera_response_t hera_submit_proposal(const hera_proposal_t *proposal);

/*
 * Get pending proposals count
 */
uint32_t hera_get_pending_proposals(void);

/* ============================================================================
 * MEMORY CORE INTERFACE
 * ============================================================================ */

/*
 * Connect to Memory Core
 */
hera_result_t hera_connect_memory_core(void);

/*
 * Order Memory Core to store an item
 * 
 * @param item_type Type (episodic, semantic, etc)
 * @param content Content to store
 * @param relevance Initial relevance
 * @param out_id Output: assigned ID
 */
hera_result_t hera_mc_store(uint8_t item_type, const char *content,
                             float relevance, uint64_t *out_id);

/*
 * Order Memory Core to promote memory to RAM
 * (Archive → Active)
 */
hera_result_t hera_mc_promote(uint64_t id);

/*
 * Order Memory Core to degrade memory to archive
 * (Active → Archive)
 */
hera_result_t hera_mc_degrade(uint64_t id);

/*
 * Order Memory Core to archive a day
 */
hera_result_t hera_mc_archive_day(int year, int month, int day);

/*
 * Order Memory Core to load a day from archive
 */
hera_result_t hera_mc_load_day(int year, int month, int day);

/* ============================================================================
 * HNF-EXT INTERFACE (Essential Memory)
 * ============================================================================ */

/*
 * Connect to HNF-EXT Manager
 */
hera_result_t hera_connect_hnf_ext(void);

/*
 * Promote a memory to HNF-EXT (essentialize)
 * Only called after HHMS validation
 * 
 * @param proposal Approved proposal
 * @return HERA_OK on success
 */
hera_result_t hera_promote_to_essential(const hera_proposal_t *proposal);

/*
 * Get essential memory count
 */
uint32_t hera_get_essential_count(void);

/*
 * Get identity hash (quick identity verification)
 */
uint32_t hera_get_identity_hash(void);

/* ============================================================================
 * HHMS - HIERARCHICAL MEMORY SYSTEM
 * ============================================================================ */

/*
 * Evaluate a memory item for potential promotion
 * 
 * @param id Memory ID
 * @param out_level Recommended level (1, 2, or 3)
 * @param out_score Evaluation score
 */
hera_result_t hera_hhms_evaluate(uint64_t id, hhms_level_t *out_level, 
                                  float *out_score);

/*
 * Get HHMS statistics
 */
hera_result_t hera_hhms_get_stats(uint32_t *out_level1_count,
                                   uint32_t *out_level2_count,
                                   uint64_t *out_level3_count);

/* ============================================================================
 * CONSOLIDATION (Sleep Cycle)
 * ============================================================================ */

/*
 * Trigger consolidation manually
 * 
 * @param out_result Output: consolidation result
 * @return HERA_OK on success
 */
hera_result_t hera_consolidate(hera_consolidation_result_t *out_result);

/*
 * Check if consolidation is needed
 */
bool hera_needs_consolidation(void);

/* ============================================================================
 * CHECKPOINT (for HEXOS Continuity)
 * ============================================================================ */

/*
 * Prepare checkpoint for HEXOS
 * 
 * @param out_checkpoint Output: checkpoint data
 * @return HERA_OK on success
 */
hera_result_t hera_prepare_checkpoint(hera_checkpoint_t *out_checkpoint);

/*
 * Restore from checkpoint
 * 
 * @param checkpoint Checkpoint to restore
 * @return HERA_OK on success
 */
hera_result_t hera_restore_checkpoint(const hera_checkpoint_t *checkpoint);

/*
 * Add stable fact to current checkpoint
 */
hera_result_t hera_add_stable_fact(const char *fact);

/*
 * Add open task to current checkpoint
 */
hera_result_t hera_add_open_task(const char *task);

/*
 * Set current user intent
 */
hera_result_t hera_set_user_intent(const char *intent);

/*
 * Set conversation summary
 */
hera_result_t hera_set_conversation_summary(const char *summary);

/* ============================================================================
 * STATISTICS
 * ============================================================================ */

/*
 * Get HERA statistics
 */
hera_result_t hera_get_stats(hera_stats_t *out_stats);

/*
 * Get current pressure level
 */
hera_pressure_t hera_get_pressure(void);

/* ============================================================================
 * IDENTITY GUARDIAN
 * ============================================================================ */

/*
 * Get Helios name
 */
const char* hera_get_name(void);

/*
 * Get Helios purpose
 */
const char* hera_get_purpose(void);

/*
 * Get continuity message for session start
 */
hera_result_t hera_get_continuity_message(char *out_message, size_t max_len);

/* ============================================================================
 * VALIDATION (HHMS Semantic Validator)
 * ============================================================================ */

/*
 * Validate a core memory proposal
 * 
 * @param proposal Proposal to validate
 * @param out_accepted Output: true if accepted
 * @param out_reason Output: reason for decision
 * @return HERA_OK on success
 */
hera_result_t hera_validate_proposal(const hera_proposal_t *proposal,
                                      bool *out_accepted,
                                      char *out_reason, size_t reason_len);

#endif /* HERA_H */
