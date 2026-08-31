-- Demo Auth users for local development
insert into auth.users (id, email, raw_user_meta_data)
values
  ('aaaaaaaa-0000-0000-0000-000000000001', 'rohan@mrpl.demo', '{}'),
  ('aaaaaaaa-0000-0000-0000-000000000002', 'priya@mrpl.demo', '{}'),
  ('aaaaaaaa-0000-0000-0000-000000000003', 'suresh@mrpl.demo', '{}'),
  ('aaaaaaaa-0000-0000-0000-000000000004', 'kavya@mrpl.demo', '{}')
on conflict (id) do nothing;

-- ============================================================
-- seed.sql
-- Realistic demo data for the 3 rehearsed scenarios:
--   1. "Summarize all safety incidents in Unit 3 in the last 6 months"
--   2. "List all SOP violations in Q2 and suggest corrective actions"
--   3. "Generate a checklist for pre-startup safety review"
--
-- HOW TO USE:
-- 1. First create your demo users via Supabase Auth (dashboard, or
--    supabase.auth.admin.createUser via the CLI/API) — you need real
--    auth.users rows before user_profiles can reference them.
-- 2. Copy the UUIDs Supabase generates and paste them into the
--    variables below (replace the placeholder UUIDs).
-- 3. Run this file: supabase db execute -f supabase/seed.sql
--    (or paste into the Supabase SQL Editor)
-- ============================================================

-- ------------------------------------------------------------
-- Units
-- ------------------------------------------------------------
insert into units (id, name) values
  ('11111111-1111-1111-1111-111111111111', 'Unit 3'),
  ('22222222-2222-2222-2222-222222222222', 'Unit 5')
on conflict (id) do nothing;

-- ------------------------------------------------------------
-- User profiles
-- ⚠️ REPLACE these UUIDs with real auth.users IDs after you create
--    the users in Supabase Auth. These placeholders will fail the
--    foreign key check otherwise.
-- ------------------------------------------------------------
insert into user_profiles (id, full_name, role, unit_id) values
  ('aaaaaaaa-0000-0000-0000-000000000001', 'Rohan Iyer',    'engineer', '11111111-1111-1111-1111-111111111111'),
  ('aaaaaaaa-0000-0000-0000-000000000002', 'Priya Nair',    'engineer', '22222222-2222-2222-2222-222222222222'),
  ('aaaaaaaa-0000-0000-0000-000000000003', 'Suresh Menon',  'manager',  '11111111-1111-1111-1111-111111111111'),
  ('aaaaaaaa-0000-0000-0000-000000000004', 'Kavya Das',     'manager',  '22222222-2222-2222-2222-222222222222')
on conflict (id) do nothing;

-- ------------------------------------------------------------
-- Incidents — deliberate cluster in Unit 3 over the last 6 months
-- so "summarize Unit 3, last 6 months" returns a coherent story
-- ------------------------------------------------------------
insert into incidents (unit_id, title, description, severity, occurred_at, reported_by) values
  ('11111111-1111-1111-1111-111111111111', 'Minor steam leak near Reactor 2',
   'Small steam leak detected at flange joint on Reactor 2 during routine inspection. Isolated and repaired within 2 hours.',
   'low', now() - interval '5 months', 'aaaaaaaa-0000-0000-0000-000000000001'),

  ('11111111-1111-1111-1111-111111111111', 'Pressure gauge malfunction, Line 4',
   'Pressure gauge on Line 4 showed erratic readings during shift changeover. Replaced faulty sensor, no product loss.',
   'medium', now() - interval '4 months', 'aaaaaaaa-0000-0000-0000-000000000001'),

  ('11111111-1111-1111-1111-111111111111', 'Near-miss: forklift collision risk',
   'Forklift operator narrowly avoided collision with pedestrian near loading bay due to blind corner. No injuries. Signage added.',
   'medium', now() - interval '3 months', 'aaaaaaaa-0000-0000-0000-000000000001'),

  ('11111111-1111-1111-1111-111111111111', 'Fire alarm false trigger, Control Room',
   'Smoke detector triggered false alarm due to dust accumulation. Evacuation drill completed in 4 minutes.',
   'low', now() - interval '2 months', 'aaaaaaaa-0000-0000-0000-000000000001'),

  ('11111111-1111-1111-1111-111111111111', 'Chemical spill, Storage Bay 2',
   'Small quantity of catalyst solution spilled during transfer. Contained per SOP, no exposure reported. Incident under review for procedural gaps.',
   'high', now() - interval '1 months', 'aaaaaaaa-0000-0000-0000-000000000001'),

  ('11111111-1111-1111-1111-111111111111', 'Unplanned shutdown, Compressor Unit',
   'Compressor tripped due to high vibration reading. Root cause traced to bearing wear. Unit restarted after 6-hour maintenance window.',
   'critical', now() - interval '10 days', 'aaaaaaaa-0000-0000-0000-000000000001'),

  -- A couple in Unit 5 too, so unit-filtering is demonstrably working
  ('22222222-2222-2222-2222-222222222222', 'Routine valve inspection flag',
   'Valve V-22 showed minor corrosion during scheduled inspection. Scheduled for replacement next maintenance cycle.',
   'low', now() - interval '3 months', 'aaaaaaaa-0000-0000-0000-000000000002');

-- ------------------------------------------------------------
-- SOP violations — Q2 2026, mixed statuses, so "list Q2 violations
-- and suggest corrective actions" has real material to work with
-- ------------------------------------------------------------
insert into sop_violations (unit_id, sop_reference, violation_desc, quarter, corrective_action, status) values
  ('11111111-1111-1111-1111-111111111111', 'SOP-14.2',
   'PPE (face shield) not worn during catalyst handling in Storage Bay 2.',
   'Q2-2026', 'Mandatory PPE checkpoint added at bay entrance; supervisor sign-off required before handling.', 'resolved'),

  ('11111111-1111-1111-1111-111111111111', 'SOP-09.1',
   'Lockout-tagout (LOTO) procedure skipped during compressor bearing inspection.',
   'Q2-2026', 'Re-training scheduled for all maintenance staff; LOTO checklist made mandatory in work order system.', 'in_progress'),

  ('11111111-1111-1111-1111-111111111111', 'SOP-22.4',
   'Fire extinguisher inspection log not updated for 2 consecutive months in Control Room.',
   'Q2-2026', 'Assign monthly log review to shift supervisor; digital reminder added to maintenance calendar.', 'resolved'),

  ('22222222-2222-2222-2222-222222222222', 'SOP-14.2',
   'Incorrect labeling on chemical storage containers in Bay 4.',
   'Q2-2026', 'Relabeling audit conducted; new labeling SOP training rolled out to Unit 5 staff.', 'open'),

  ('22222222-2222-2222-2222-222222222222', 'SOP-31.0',
   'Confined space entry permit not filed before tank inspection.',
   'Q2-2026', 'Permit-to-work system flagged for mandatory digital sign-off before entry is logged.', 'open');

-- ------------------------------------------------------------
-- Sample checklist — pre-startup safety review, already generated
-- (shows the agent's expected output format for scenario 3)
-- ------------------------------------------------------------
insert into checklists (unit_id, checklist_type, items, generated_by) values
  ('11111111-1111-1111-1111-111111111111', 'pre_startup_safety_review',
   '[
     {"item": "Confirm all LOTO tags removed and equipment de-isolated", "checked": true, "notes": ""},
     {"item": "Verify pressure relief valves tested within last 12 months", "checked": true, "notes": ""},
     {"item": "Check fire suppression system operational status", "checked": true, "notes": ""},
     {"item": "Confirm emergency shutdown (ESD) system tested", "checked": false, "notes": "Pending sign-off from instrumentation team"},
     {"item": "Verify all personnel briefed on startup sequence", "checked": true, "notes": ""},
     {"item": "Confirm no open SOP violations for this unit", "checked": false, "notes": "SOP-09.1 still in_progress — flag to shift manager"}
   ]'::jsonb,
   'aaaaaaaa-0000-0000-0000-000000000003');
