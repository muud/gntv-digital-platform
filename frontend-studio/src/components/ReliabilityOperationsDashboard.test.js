import assert from "node:assert/strict";
import test from "node:test";

import {
  RELIABILITY_TABS,
  safeReliabilityText,
  summarizeReliabilityMetrics
} from "./ReliabilityOperationsDashboard.js";

test("includes the expected Reliability operator views", () => {
  const ids = RELIABILITY_TABS.map(([id]) => id);
  assert.deepEqual(ids, [
    "overview",
    "incidents",
    "recovery",
    "alerts",
    "backups"
  ]);
});

test("escapes unsafe text before rendering Reliability data", () => {
  assert.equal(
    safeReliabilityText(`<script>alert("token")</script>`),
    "&lt;script&gt;alert(&quot;token&quot;)&lt;/script&gt;"
  );
  assert.equal(
    safeReliabilityText(`' or 1=1 --`),
    "&#39; or 1=1 --"
  );
});

test("summarizes Reliability metrics properly", () => {
  const summary = summarizeReliabilityMetrics({
    healthy_component_count: 10,
    degraded_component_count: 1,
    unhealthy_component_count: 0,
    unresolved_incident_count: 2,
    active_recovery_runs: 1,
    dr_readiness: "READY"
  });
  assert.deepEqual(summary, [
    ["Healthy Services", 10],
    ["Degraded Services", 1],
    ["Unhealthy Services", 0],
    ["Open Incidents", 2],
    ["Active Recoveries", 1],
    ["DR Readiness", "READY"]
  ]);
});

test("handles empty metrics gracefully with safe fallbacks", () => {
  const summary = summarizeReliabilityMetrics({});
  assert.deepEqual(summary, [
    ["Healthy Services", 0],
    ["Degraded Services", 0],
    ["Unhealthy Services", 0],
    ["Open Incidents", 0],
    ["Active Recoveries", 0],
    ["DR Readiness", "NOT_READY"]
  ]);
});
