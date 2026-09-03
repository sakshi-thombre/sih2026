-- ============================================================
-- 0004_agent_run_tracking.sql
-- Extends the existing agent_action_logs table so it can back the
-- FastAPI backend's RunStore/ActionStore interfaces (run lifecycle +
-- per-action audit trail), instead of introducing separate
-- agent_runs / agent_run_actions tables.
--
-- `id` (already the primary key) doubles as the run id. The
-- previously single-row-per-completed-run shape is extended with
-- lifecycle/status columns and a per-run `actions` log, appended to
-- atomically via append_agent_action() rather than a read-modify-write
-- from the application, so concurrent tool calls on the same run
-- can't clobber each other's action records.
-- ============================================================

alter table agent_action_logs
  add column request_id uuid,
  add column role text check (role in ('engineer', 'manager')),
  add column context jsonb not null default '{}'::jsonb,
  add column status text not null default 'completed'
    check (status in ('created', 'queued', 'running', 'completed', 'failed', 'cancelled')),
  add column started_at timestamptz,
  add column completed_at timestamptz,
  add column error_code text,
  add column error_message text,
  add column sources jsonb not null default '[]'::jsonb,
  add column actions jsonb not null default '[]'::jsonb;

-- ------------------------------------------------------------
-- Previously only select/insert existed on agent_action_logs, so a
-- run's status/action history could never be updated after creation
-- under RLS — this is the concrete blocker that requires adding an
-- update policy (not weakening any existing one). Same ownership
-- rule as the existing select/insert policies.
-- ------------------------------------------------------------
create policy "logs_update" on agent_action_logs
  for update using (auth_role() = 'manager' or user_id = auth.uid())
  with check (auth_role() = 'manager' or user_id = auth.uid());

-- ------------------------------------------------------------
-- Atomic append to the per-run action log. security invoker means it
-- runs with the caller's own privileges, so the update policy above
-- (and RLS in general) still applies exactly as if the caller issued
-- the UPDATE directly — this function only exists to make the append
-- a single statement instead of a race-prone read-modify-write.
-- ------------------------------------------------------------
create or replace function append_agent_action(
  p_run_id uuid,
  p_event_type text,
  p_metadata jsonb
) returns void
language sql
security invoker
as $$
  update agent_action_logs
  set actions = actions || jsonb_build_object(
    'event_type', p_event_type,
    'timestamp', to_char(now() at time zone 'utc', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"'),
    'metadata', coalesce(p_metadata, '{}'::jsonb)
  )
  where id = p_run_id;
$$;

grant execute on function append_agent_action(uuid, text, jsonb) to authenticated, service_role;
