import assert from "node:assert/strict";
import test from "node:test";

import { formatCorrelationId, summarizeEventMetrics } from "./EventAutomationDashboard.js";

test("formats trace correlation identifiers without exposing full long values", () => {
  assert.equal(formatCorrelationId("12345678-1234-1234-1234-123456789012"), "12345678…789012");
  assert.equal(formatCorrelationId(null), "—");
});

test("summarizes safe operations metrics", () => {
  const summary = summarizeEventMetrics({ events_received: 12, events_processed: 10, dead_letter_count: 1 });
  assert.deepEqual(summary[0], ["Events Received", 12]);
  assert.deepEqual(summary[1], ["Processed", 10]);
  assert.deepEqual(summary[4], ["Dead Letters", 1]);
});

