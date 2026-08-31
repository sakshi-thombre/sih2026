-- ============================================================
-- 0003_analytics_views.sql
-- Views the agent's "SQL query runner" tool will hit for
-- summarization / filtering tasks
-- ============================================================

-- security_invoker means the view respects the CALLING user's RLS,
-- not the view creator's — critical so engineer/manager scoping still applies
create view v_incident_summary
with (security_invoker = true) as
select
  i.unit_id,
  u.name as unit_name,
  i.severity,
  date_trunc('month', i.occurred_at) as month,
  count(*) as incident_count
from incidents i
join units u on u.id = i.unit_id
group by i.unit_id, u.name, i.severity, date_trunc('month', i.occurred_at);

create view v_sop_violation_summary
with (security_invoker = true) as
select
  s.unit_id,
  u.name as unit_name,
  s.quarter,
  s.status,
  count(*) as violation_count
from sop_violations s
join units u on u.id = s.unit_id
group by s.unit_id, u.name, s.quarter, s.status;

-- Convenience view: recent incidents in plain-language-friendly shape,
-- good for the RAG/summarization tool to pull directly
create view v_recent_incidents
with (security_invoker = true) as
select
  i.id,
  u.name as unit_name,
  i.title,
  i.description,
  i.severity,
  i.occurred_at
from incidents i
join units u on u.id = i.unit_id
order by i.occurred_at desc;
