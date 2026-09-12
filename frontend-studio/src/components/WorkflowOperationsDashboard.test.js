import assert from "node:assert/strict";
import test from "node:test";

import { collectPendingApprovals, formatWorkflowDuration } from "./WorkflowOperationsDashboard.js";

test("formats completed and active workflow durations", () => {
  assert.equal(formatWorkflowDuration("2026-09-11T10:00:00Z", "2026-09-11T10:01:05Z"), "1m 5s");
  assert.equal(formatWorkflowDuration("2026-09-11T10:00:00Z", null, Date.parse("2026-09-11T10:00:12Z")), "12s");
  assert.equal(formatWorkflowDuration(null, null), "—");
});

test("collects only runs waiting for manual approval", () => {
  const runs = [{ status: "running" }, { status: "waiting", id: "a" }, { status: "failed" }];
  assert.deepEqual(collectPendingApprovals(runs), [{ status: "waiting", id: "a" }]);
});
