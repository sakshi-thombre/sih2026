-- ============================================================
-- 0001_schema.sql
-- Core schema for Sovereign On-Premise Agentic AI Workbench (SIH26117)
-- Person D (DB/Auth) — Aanya
-- ============================================================

create extension if not exists "pgcrypto"; -- for gen_random_uuid()

-- ------------------------------------------------------------
-- Org structure
-- ------------------------------------------------------------
create table units (
  id uuid primary key default gen_random_uuid(),
  name text not null unique,          -- 'Unit 3', 'Unit 5', etc.
  created_at timestamptz default now()
);

-- Extends Supabase's built-in auth.users with app-specific fields
create table user_profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  full_name text not null,
  role text not null check (role in ('engineer','manager')),
  unit_id uuid references units(id),
  created_at timestamptz default now()
);

-- ------------------------------------------------------------
-- Scenario 1: incident summaries
-- ------------------------------------------------------------
create table incidents (
  id uuid primary key default gen_random_uuid(),
  unit_id uuid references units(id) not null,
  title text not null,
  description text not null,
  severity text not null check (severity in ('low','medium','high','critical')),
  occurred_at timestamptz not null,
  reported_by uuid references user_profiles(id),
  created_at timestamptz default now()
);

create index idx_incidents_unit_time on incidents (unit_id, occurred_at desc);

-- ------------------------------------------------------------
-- Scenario 2: SOP violations
-- ------------------------------------------------------------
create table sop_violations (
  id uuid primary key default gen_random_uuid(),
  unit_id uuid references units(id) not null,
  sop_reference text not null,        -- e.g. 'SOP-14.2'
  violation_desc text not null,
  quarter text not null,              -- 'Q2-2026'
  corrective_action text,
  status text not null default 'open' check (status in ('open','in_progress','resolved')),
  created_at timestamptz default now()
);

create index idx_sop_unit_quarter on sop_violations (unit_id, quarter);

-- ------------------------------------------------------------
-- Scenario 3: checklist generation
-- ------------------------------------------------------------
create table checklists (
  id uuid primary key default gen_random_uuid(),
  unit_id uuid references units(id) not null,
  checklist_type text not null,       -- 'pre_startup_safety_review'
  items jsonb not null,               -- [{ "item": "...", "checked": false, "notes": "" }, ...]
  generated_by uuid references user_profiles(id),
  created_at timestamptz default now()
);

-- ------------------------------------------------------------
-- Agent audit log (every action the agent takes)
-- ------------------------------------------------------------
create table agent_action_logs (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references user_profiles(id),
  task_input text not null,
  plan jsonb,                         -- structured step breakdown
  tools_used text[],                  -- e.g. '{doc_search, sql_query}'
  final_output text,
  created_at timestamptz default now()
);

create index idx_logs_user_time on agent_action_logs (user_id, created_at desc);
