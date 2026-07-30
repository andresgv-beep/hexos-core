/*
 * COGNITIVE KERNEL v3.0 - Stub API
 * HELIOS Cognitive Ecosystem
 * 
 * This is a STUB implementation for testing the ecosystem
 * without a real LLM/CUDA backend.
 * 
 * The CK organizes thought:
 *   • CK_PERCEIVE: Input parsing, intent classification
 *   • CK_REMEMBER: Memory query, context building
 *   • CK_THINK: Reasoning, planning
 *   • CK_REFLECT: Learning, proposal generation
 *   • CK_EXPRESS: Response generation
 *   • CK_SIGNAL: Communication with HERA/HEXOS
 */

#ifndef COGNITIVE_KERNEL_H
#define COGNITIVE_KERNEL_H

#include "ck_types.h"

/* ============================================================================
 * LIFECYCLE
 * ============================================================================ */

/*
 * Initialize Cognitive Kernel
 */
ck_result_t ck_init(const ck_config_t *config);

/*
 * Shutdown Cognitive Kernel
 */
void ck_shutdown(void);

/*
 * Check if initialized
 */
bool ck_is_initialized(void);

/*
 * Get current state
 */
ck_state_t ck_get_state(void);

/* ============================================================================
 * CONNECTIONS
 * ============================================================================ */

/*
 * Connect to HERA
 */
ck_result_t ck_connect_hera(void);

/*
 * Connect to HEXOS
 */
ck_result_t ck_connect_hexos(void);

/* ============================================================================
 * MAIN PROCESSING (TURN CYCLE)
 * ============================================================================ */

/*
 * Process a complete turn (input → output)
 * 
 * @param input User input text
 * @param out_turn Output: complete turn data
 * @return CK_OK on success
 */
ck_result_t ck_process_turn(const char *input, ck_turn_t *out_turn);

/*
 * Process turn step by step (for detailed control)
 */
ck_result_t ck_begin_turn(const char *input, ck_turn_t *turn);
ck_result_t ck_perceive(ck_turn_t *turn);
ck_result_t ck_remember(ck_turn_t *turn);
ck_result_t ck_think(ck_turn_t *turn);
ck_result_t ck_express(ck_turn_t *turn);
ck_result_t ck_reflect(ck_turn_t *turn);
ck_result_t ck_end_turn(ck_turn_t *turn);

/* ============================================================================
 * CK_PERCEIVE
 * ============================================================================ */

/*
 * Parse input text
 */
ck_result_t ck_parse_input(const char *text, ck_parsed_input_t *out_parsed);

/*
 * Classify intent
 */
ck_result_t ck_classify_intent(const ck_parsed_input_t *input, ck_intent_t *out_intent);

/*
 * Extract semantic tags
 */
ck_result_t ck_extract_tags(const ck_parsed_input_t *input, 
                             const ck_intent_t *intent,
                             ck_semantic_tags_t *out_tags);

/* ============================================================================
 * CK_REMEMBER
 * ============================================================================ */

/*
 * Query memories relevant to input
 * (Delegates to HERA)
 */
ck_result_t ck_query_memories(const float *embedding, 
                               uint16_t dim,
                               ck_memory_ref_t *out_memories,
                               uint8_t max_memories,
                               uint8_t *out_count);

/*
 * Build context from memories and identity
 */
ck_result_t ck_build_context(const ck_memory_ref_t *memories,
                              uint8_t memory_count,
                              ck_context_t *out_context);

/* ============================================================================
 * CK_THINK
 * ============================================================================ */

/*
 * Perform reasoning on input + context
 */
ck_result_t ck_reason(const ck_parsed_input_t *input,
                       const ck_context_t *context,
                       ck_reasoning_step_t *out_steps,
                       uint8_t max_steps,
                       uint8_t *out_count);

/* ============================================================================
 * CK_EXPRESS
 * ============================================================================ */

/*
 * Generate response
 */
ck_result_t ck_generate_response(const ck_turn_t *turn, ck_response_t *out_response);

/*
 * Adapt style based on user preferences
 */
ck_result_t ck_adapt_style(const ck_semantic_tags_t *tags, ck_style_t *out_style);

/* ============================================================================
 * CK_REFLECT
 * ============================================================================ */

/*
 * Analyze interaction for learnings
 */
ck_result_t ck_analyze_turn(const ck_turn_t *turn,
                             ck_learning_t *out_learnings,
                             uint8_t max_learnings,
                             uint8_t *out_count);

/*
 * Generate core memory proposal if warranted
 */
ck_result_t ck_generate_proposal(const ck_turn_t *turn, 
                                  ck_proposal_t *out_proposal,
                                  bool *out_has_proposal);

/* ============================================================================
 * CK_SIGNAL
 * ============================================================================ */

/*
 * Submit proposal to HERA
 */
ck_result_t ck_submit_proposal_to_hera(const ck_proposal_t *proposal);

/*
 * Notify HERA of context update
 */
ck_result_t ck_notify_context_update(void);

/*
 * Notify HERA of turn completion
 */
ck_result_t ck_notify_turn_complete(void);

/* ============================================================================
 * IDENTITY
 * ============================================================================ */

/*
 * Get Helios name
 */
const char* ck_get_name(void);

/*
 * Get Helios purpose
 */
const char* ck_get_purpose(void);

/*
 * Get current style profile
 */
ck_result_t ck_get_style(ck_style_t *out_style);

/*
 * Set style profile
 */
ck_result_t ck_set_style(const ck_style_t *style);

/* ============================================================================
 * STATISTICS
 * ============================================================================ */

/*
 * Get statistics
 */
ck_result_t ck_get_stats(ck_stats_t *out_stats);

/* ============================================================================
 * UTILITY
 * ============================================================================ */

/*
 * Get intent type name
 */
const char* ck_intent_name(ck_intent_type_t intent);

/*
 * Get state name
 */
const char* ck_state_name(ck_state_t state);

#endif /* COGNITIVE_KERNEL_H */
