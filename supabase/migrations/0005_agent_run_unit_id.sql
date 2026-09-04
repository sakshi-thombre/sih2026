-- ============================================================
-- 0005_agent_run_unit_id.sql
-- Adds unit_id to agent_action_logs so an agent run's unit is
-- persisted at creation time (see app.runs.models.AgentRun) and can
-- be read back as trusted context when Person C's agent service later
-- calls POST /api/v1/agent/tools/execute — that request carries no
-- end-user JWT, only a run_id, so the run row is the only place this
-- can safely come from. Never populated from agent- or tool-supplied
-- input.
-- ============================================================

alter table agent_action_logs
  add column unit_id uuid references units(id);
