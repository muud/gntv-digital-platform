import assert from "node:assert/strict";
import test from "node:test";

import { AGENT_TABS, safeAgentText, summarizeAgentMetrics } from "./AgentControlDashboard.js";

test("agent studio exposes every required operations view", () => {
  assert.deepEqual(AGENT_TABS.map((tab) => tab[1]), ["Overview", "Agents", "Runs", "Tool Calls", "Approvals", "Model Policies", "Tool Policies", "Approval Policies", "Audit / Trace"]);
});

test("agent metrics remain stable for sparse responses", () => {
  assert.deepEqual(summarizeAgentMetrics({ active_agents: 2 })[0], ["Active Agents", 2]);
  assert.deepEqual(summarizeAgentMetrics({})[7], ["Blocked", 0]);
});

test("agent UI escapes untrusted output and errors", () => {
  assert.equal(safeAgentText('<script token="secret">'), "&lt;script token=&quot;secret&quot;&gt;");
});
