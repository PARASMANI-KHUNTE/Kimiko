"""DateTime tool — provides the current date and time to the agent.

No external dependencies. Returns ISO 8601 formatted datetime in UTC and
the user-friendly local representation.
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta

from pydantic import BaseModel, Field

from kimiko.tools.base import BaseTool


class DateTimeInput(BaseModel):
    timezone_offset_hours: float = Field(
        default=0.0,
        description="UTC offset in hours (e.g., 5.5 for IST, -5 for EST). Defaults to UTC.",
    )


class DateTimeTool(BaseTool):
    """Returns the current date and time. Use this whenever the user asks about the current time, date, or day."""

    def __init__(self) -> None:
        super().__init__(
            name="get_datetime",
            description=(
                "Get the current date, time, and day of the week. "
                "Use this when the user asks what time it is, what today's date is, "
                "or any question requiring knowledge of the current moment."
            ),
            capabilities=["datetime", "realtime"],
        )

    @property
    def args_schema(self) -> type[BaseModel]:
        return DateTimeInput

    async def run(self, timezone_offset_hours: float = 0.0) -> str:
        """Return the current datetime in both UTC and the requested timezone."""
        utc_now = datetime.now(timezone.utc)

        if timezone_offset_hours != 0.0:
            tz = timezone(timedelta(hours=timezone_offset_hours))
            local_now = utc_now.astimezone(tz)
            offset_str = f"UTC{'+' if timezone_offset_hours >= 0 else ''}{timezone_offset_hours:g}"
            return (
                f"Current datetime:\n"
                f"  UTC:   {utc_now.strftime('%Y-%m-%d %H:%M:%S')} UTC\n"
                f"  Local ({offset_str}): {local_now.strftime('%Y-%m-%d %H:%M:%S %Z')}\n"
                f"  Day:   {local_now.strftime('%A, %B %d, %Y')}"
            )

        return (
            f"Current datetime:\n"
            f"  UTC:  {utc_now.strftime('%Y-%m-%d %H:%M:%S')} UTC\n"
            f"  Day:  {utc_now.strftime('%A, %B %d, %Y')}"
        )
