import assert from "node:assert/strict";
import test from "node:test";

import { JOB_TABS, formatDuration, summarizeJobMetrics } from "./BackgroundJobsDashboard.js";

test("background operations exposes every required view", () => {
  assert.deepEqual(JOB_TABS.map((tab) => tab[1]), ["Queue Overview", "Jobs", "Workers", "Schedules", "Retry Queue", "Dead Letter Jobs"]);
});

test("job metric summaries are stable for sparse API responses", () => {
  assert.deepEqual(summarizeJobMetrics({ queued_jobs: 2, dead_letter_jobs: 1 })[0], ["Queued", 2]);
  assert.deepEqual(summarizeJobMetrics({ queued_jobs: 2, dead_letter_jobs: 1 })[5], ["Dead Letter", 1]);
});

test("duration formatting handles pending and completed jobs", () => {
  assert.equal(formatDuration({}), "—");
  assert.equal(formatDuration({ started_at: "2026-01-01T00:00:00Z", completed_at: "2026-01-01T00:00:02Z" }), "2.0s");
});
