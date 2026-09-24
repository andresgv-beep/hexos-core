export interface InferenceMetrics {
  contextUsed: number | null;
  contextCapacity: number | null;
  tokensPerSecond: number | null;
}

export function parseInferenceMetrics(value: unknown): InferenceMetrics {
  const data = value && typeof value === "object" ? value as Record<string, unknown> : {};
  const valid = (n: unknown): n is number => typeof n === "number" && Number.isFinite(n) && n >= 0;
  return {
    contextUsed: valid(data.context_used) && Number.isInteger(data.context_used) ? data.context_used : null,
    contextCapacity: valid(data.context_capacity) && Number.isInteger(data.context_capacity) && data.context_capacity > 0 ? data.context_capacity : null,
    tokensPerSecond: valid(data.tokens_per_second) ? data.tokens_per_second : null,
  };
}
