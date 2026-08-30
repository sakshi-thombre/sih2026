-- ============================================================
-- 0002_rls_policies.sql
-- Row Level Security: engineers see their own unit, managers see all
-- ============================================================

-- ------------------------------------------------------------
-- Helper functions (SECURITY DEFINER so they can read user_profiles
-- even though the row-level policies below will restrict direct access)
-- ------------------------------------------------------------
create or replace function auth_role() returns text
language sql stable security definer
set search_path = public
as $$
  select role from user_profiles where id = auth.uid();
$$;

create or replace function auth_unit() returns uuid
language sql stable security definer
set search_path = public
as $$
  select unit_id from user_profiles where id = auth.uid();
$$;

-- ------------------------------------------------------------
-- Enable RLS on every table
-- ------------------------------------------------------------
alter table units enable row level security;
alter table user_profiles enable row level security;
alter table incidents enable row level security;
alter table sop_violations enable row level security;
alter table checklists enable row level security;
alter table agent_action_logs enable row level security;

-- ------------------------------------------------------------
-- units: everyone authenticated can read (needed for dropdowns etc.)
-- ------------------------------------------------------------
create policy "units_select_all" on units
  for select using (auth.role() = 'authenticated');

-- ------------------------------------------------------------
-- user_profiles: users see their own row; managers see everyone
-- ------------------------------------------------------------
create policy "profiles_select" on user_profiles
  for select using (id = auth.uid() or auth_role() = 'manager');

create policy "profiles_update_self" on user_profiles
  for update using (id = auth.uid());

-- ------------------------------------------------------------
-- incidents
-- ------------------------------------------------------------
create policy "incidents_select" on incidents
  for select using (auth_role() = 'manager' or unit_id = auth_unit());

create policy "incidents_insert" on incidents
  for insert with check (auth_role() = 'manager' or unit_id = auth_unit());

create policy "incidents_update" on incidents
  for update using (auth_role() = 'manager' or unit_id = auth_unit());

-- ------------------------------------------------------------
-- sop_violations
-- ------------------------------------------------------------
create policy "sop_select" on sop_violations
  for select using (auth_role() = 'manager' or unit_id = auth_unit());

create policy "sop_insert" on sop_violations
  for insert with check (auth_role() = 'manager' or unit_id = auth_unit());

create policy "sop_update" on sop_violations
  for update using (auth_role() = 'manager' or unit_id = auth_unit());

-- ------------------------------------------------------------
-- checklists
-- ------------------------------------------------------------
create policy "checklists_select" on checklists
  for select using (auth_role() = 'manager' or unit_id = auth_unit());

create policy "checklists_insert" on checklists
  for insert with check (auth_role() = 'manager' or unit_id = auth_unit());

-- ------------------------------------------------------------
-- agent_action_logs: users see their own actions; managers see all
-- (this is the audit trail — managers need full visibility for trust/compliance)
-- ------------------------------------------------------------
create policy "logs_select" on agent_action_logs
  for select using (auth_role() = 'manager' or user_id = auth.uid());

create policy "logs_insert" on agent_action_logs
  for insert with check (user_id = auth.uid());
