"""Safe incident query tool exposed to the agent service.

This intentionally does not execute arbitrary SQL. The agent supplies a
natural-language query description; this tool maps the supported filters to
Supabase query-builder operations and always applies the run caller's unit
scope. Managers may query across units; engineers are restricted to their
own unit.
"""
import re
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from app.db.session import get_service_db
from app.tools.base import Tool, ToolResult


class SQLQueryInput(BaseModel):
    query: str = Field(..., min_length=1, max_length=4000)


class SQLQueryTool(Tool):
    name = "sql_query"
    description = "Query structured incident records with safe filters."
    input_schema = SQLQueryInput
    required_role = None

    async def run(self, input_data: BaseModel, *, caller: dict[str, str]) -> ToolResult:
        assert isinstance(input_data, SQLQueryInput)
        query = input_data.query.lower()
        db = get_service_db()

        try:
            builder = db.table("incidents").select(
                "id,unit_id,title,description,severity,occurred_at,created_at"
            )

            role = caller.get("role")
            caller_unit_id = caller.get("unit_id") or ""

            if role != "manager":
                if not caller_unit_id:
                    return ToolResult(
                        success=False,
                        error="No unit assigned to this account; incident query is unavailable",
                    )
                builder = builder.eq("unit_id", caller_unit_id)
            else:
                # Managers may optionally filter by an explicit UUID or unit name.
                unit_match = re.search(r"unit(?:\s+id)?\s*[:=]?\s*([0-9a-f-]{36})", query)
                if unit_match:
                    builder = builder.eq("unit_id", unit_match.group(1))
                else:
                    name_match = re.search(r"\bunit\s+([a-z0-9_-]+)", query)
                    if name_match:
                        unit_name = f"Unit {name_match.group(1)}"
                        unit = await db.table("units").select("id").ilike("name", unit_name).maybe_single().execute()
                        if unit.data:
                            builder = builder.eq("unit_id", unit.data["id"])

            for severity in ("critical", "high", "medium", "low"):
                if re.search(rf"\b{severity}\b", query):
                    builder = builder.eq("severity", severity)
                    break

            # Support common explicit date ranges; otherwise return newest records first.
            dates = re.findall(r"\b(20\d{2}-\d{2}-\d{2})\b", query)
            if len(dates) >= 2:
                builder = builder.gte("occurred_at", f"{dates[0]}T00:00:00Z")
                builder = builder.lte("occurred_at", f"{dates[1]}T23:59:59Z")
            elif len(dates) == 1:
                builder = builder.gte("occurred_at", f"{dates[0]}T00:00:00Z")

            builder = builder.order("occurred_at", desc=True).limit(100)
            response = await builder.execute()
            return ToolResult(success=True, data=response.data or [])
        except Exception:
            return ToolResult(success=False, error="Incident query is currently unavailable")
