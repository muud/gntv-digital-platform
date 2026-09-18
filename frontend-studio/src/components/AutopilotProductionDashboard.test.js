import assert from "node:assert/strict";
import test from "node:test";

import {
  AUTOPILOT_TABS,
  safeAutopilotText,
  summarizeAutopilotMetrics
} from "./AutopilotProductionDashboard.js";

test("includes the expected Autopilot operator views", () => {
  const ids = AUTOPILOT_TABS.map(([id]) => id);
  assert.deepEqual(ids, [
    "overview",
    "productions",
    "approvals",
    "publishing",
    "destinations",
    "trace"
  ]);
});

test("escapes unsafe text before rendering Autopilot data", () => {
  assert.equal(
    safeAutopilotText(`<script>alert("token")</script>`),
    "&lt;script&gt;alert(&quot;token&quot;)&lt;/script&gt;"
  );
});

test("summarizes Autopilot metrics without fabricated fallback data", () => {
  const summary = summarizeAutopilotMetrics({
    productions_by_state: { draft: 2, published: 1 },
    awaiting_approval: 3,
    publishing_queue_depth: 4,
    scheduled_publications: 5,
    partial_publishing_count: 6
  });
  assert.deepEqual(summary, [
    ["Draft", 2],
    ["Awaiting Approval", 3],
    ["Publishing Queue", 4],
    ["Scheduled", 5],
    ["Partial", 6],
    ["Published", 1]
  ]);
});
