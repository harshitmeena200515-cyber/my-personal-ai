"""
DateTime Tool.

Provides current time, date calculations, timezone info, and formatting.
No side effects.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from tools.base import BaseTool, ToolResult, ToolParameter, PermissionLevel


class DateTimeTool(BaseTool):
    """Date and time utility.

    Returns current time, performs date arithmetic, and formats dates.
    No side effects.
    """

    name = "datetime"
    description = (
        "Get current date/time, perform date arithmetic (add/subtract days/hours), "
        "or format dates. No side effects."
    )
    category = "utility"
    permission = PermissionLevel.SAFE
    parameters = [
        ToolParameter(
            name="action",
            type="string",
            description="'now' (current time), 'add' (add duration), 'diff' (difference between dates), 'format' (format a date)",
            required=False,
            default="now",
        ),
        ToolParameter(
            name="days",
            type="number",
            description="Days to add/subtract (for 'add' action). Negative to subtract.",
            required=False,
            default=0,
        ),
        ToolParameter(
            name="hours",
            type="number",
            description="Hours to add/subtract (for 'add' action).",
            required=False,
            default=0,
        ),
        ToolParameter(
            name="date_str",
            type="string",
            description="ISO date string (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS) for 'format' or 'diff'.",
            required=False,
        ),
        ToolParameter(
            name="date_str_2",
            type="string",
            description="Second ISO date string for 'diff' action.",
            required=False,
        ),
    ]

    async def execute(self, params: Dict[str, Any]) -> ToolResult:
        action = str(params.get("action", "now")).lower()

        if action == "now":
            return self._now()
        elif action == "add":
            return self._add(params)
        elif action == "diff":
            return self._diff(params)
        elif action == "format":
            return self._format(params)
        else:
            return ToolResult(success=False, error=f"Unknown action: '{action}'. Use 'now', 'add', 'diff', or 'format'.")

    def _now(self) -> ToolResult:
        now = datetime.now()
        utc_now = datetime.now(timezone.utc)
        return ToolResult(
            success=True,
            output={
                "local": now.isoformat(),
                "utc": utc_now.isoformat(),
                "date": now.strftime("%Y-%m-%d"),
                "time": now.strftime("%H:%M:%S"),
                "day_of_week": now.strftime("%A"),
                "timestamp": int(now.timestamp()),
            },
        )

    def _add(self, params: Dict[str, Any]) -> ToolResult:
        days = float(params.get("days", 0))
        hours = float(params.get("hours", 0))

        if abs(days) > 36500 or abs(hours) > 876000:
            return ToolResult(success=False, error="Duration too large. Max: 100 years.")

        base_str = params.get("date_str")
        if base_str:
            try:
                base = datetime.fromisoformat(str(base_str))
            except ValueError:
                return ToolResult(success=False, error=f"Invalid date format: '{base_str}'. Use ISO format (YYYY-MM-DD).")
        else:
            base = datetime.now()

        result = base + timedelta(days=days, hours=hours)
        return ToolResult(
            success=True,
            output={
                "base": base.isoformat(),
                "added": f"{days} days, {hours} hours",
                "result": result.isoformat(),
                "day_of_week": result.strftime("%A"),
            },
        )

    def _diff(self, params: Dict[str, Any]) -> ToolResult:
        date1_str = params.get("date_str")
        date2_str = params.get("date_str_2")

        if not date1_str or not date2_str:
            return ToolResult(success=False, error="Both 'date_str' and 'date_str_2' are required for 'diff'.")

        try:
            d1 = datetime.fromisoformat(str(date1_str))
            d2 = datetime.fromisoformat(str(date2_str))
        except ValueError as e:
            return ToolResult(success=False, error=f"Invalid date format: {e}")

        delta = d2 - d1
        return ToolResult(
            success=True,
            output={
                "date_1": d1.isoformat(),
                "date_2": d2.isoformat(),
                "difference_days": delta.days,
                "difference_seconds": int(delta.total_seconds()),
                "difference_hours": round(delta.total_seconds() / 3600, 2),
            },
        )

    def _format(self, params: Dict[str, Any]) -> ToolResult:
        date_str = params.get("date_str")
        if not date_str:
            return ToolResult(success=False, error="Parameter 'date_str' is required for 'format'.")

        try:
            dt = datetime.fromisoformat(str(date_str))
        except ValueError:
            return ToolResult(success=False, error=f"Invalid date format: '{date_str}'")

        return ToolResult(
            success=True,
            output={
                "iso": dt.isoformat(),
                "human": dt.strftime("%B %d, %Y at %I:%M %p"),
                "date_only": dt.strftime("%Y-%m-%d"),
                "time_only": dt.strftime("%H:%M:%S"),
                "day": dt.strftime("%A"),
                "timestamp": int(dt.timestamp()),
            },
        )
