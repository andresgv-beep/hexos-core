import { test } from "node:test";
import assert from "node:assert/strict";
import { parseInferenceMetrics } from "../lib/helios/metrics";

test("metrics preserve real zero and reject missing or invalid measurements", () => {
  assert.deepEqual(parseInferenceMetrics({context_used: 0, context_capacity: 16384, tokens_per_second: 38.2}),
    {contextUsed: 0, contextCapacity: 16384, tokensPerSecond: 38.2});
  assert.deepEqual(parseInferenceMetrics({context_used: -1, context_capacity: 0, tokens_per_second: Infinity}),
    {contextUsed: null, contextCapacity: null, tokensPerSecond: null});
  assert.equal(parseInferenceMetrics(undefined).contextUsed, null);
});
