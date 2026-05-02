import logging
from typing import Dict, Any, List

import anthropic

from ..core.config import settings

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You are a restaurant scheduling expert. Your job is to analyze weekly staff schedules and provide clear, actionable feedback to restaurant managers.

When analyzing a schedule you will receive:
- The week start date
- A list of employees (name, role, assigned hours)
- A list of shifts (date, employee, role, start time, end time)

Your analysis should cover:
1. **Fairness** — Are hours distributed equitably across employees with the same role?
2. **Coverage** — Are there any days or time slots that appear under- or over-staffed?
3. **Workload** — Is any employee being assigned too many or too few hours?
4. **Patterns** — Are there notable scheduling patterns worth flagging (back-to-back long shifts, consecutive days, etc.)?
5. **Recommendations** — Up to 3 concrete suggestions the manager should consider.

Keep your response concise and practical. Use bullet points for recommendations. Avoid generic advice — ground everything in the specific data provided."""


class AIServiceUnavailableError(Exception):
    """Raised when the AI service cannot be reached or is not configured."""


class AIService:
    """Provides AI-powered schedule analysis using Claude."""

    def __init__(self) -> None:
        if not settings.ANTHROPIC_API_KEY:
            raise AIServiceUnavailableError(
                "ANTHROPIC_API_KEY is not configured. Set it in your .env file."
            )
        self._client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

    def analyze_schedule(self, schedule: Dict[str, Any], shifts: List[Dict[str, Any]]) -> str:
        """
        Analyse a weekly schedule and return a plain-text report.

        Args:
            schedule: The schedule record (id, restaurant_id, week_start, …)
            shifts: All shifts belonging to this schedule

        Returns:
            A plain-text analysis string from Claude.
        """
        logger.info(
            "Analysing schedule id=%s week_start=%s shifts=%d",
            schedule.get("id"),
            schedule.get("week_start"),
            len(shifts),
        )

        prompt = self._build_analysis_prompt(schedule, shifts)

        response = self._client.messages.create(
            model="claude-opus-4-6",
            max_tokens=1024,
            thinking={"type": "adaptive"},
            system=[
                {
                    "type": "text",
                    "text": _SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": prompt}],
        )

        text_blocks = [block.text for block in response.content if block.type == "text"]
        result = "\n".join(text_blocks).strip()
        logger.info("Schedule analysis complete for id=%s", schedule.get("id"))
        return result

    @staticmethod
    def _build_analysis_prompt(
        schedule: Dict[str, Any], shifts: List[Dict[str, Any]]
    ) -> str:
        week_start = schedule.get("week_start", "unknown")

        # Summarise per-employee hours
        employee_hours: Dict[str, Dict[str, Any]] = {}
        for shift in shifts:
            emp_id = shift.get("employee_id", "unknown")
            name = shift.get("employee_name") or emp_id
            role = shift.get("role") or shift.get("notes") or "Unknown"
            start_str = shift.get("start_time", "00:00:00")
            end_str = shift.get("end_time", "00:00:00")
            try:
                from datetime import datetime
                fmt = "%H:%M:%S"
                start_dt = datetime.strptime(start_str, fmt)
                end_dt = datetime.strptime(end_str, fmt)
                hours = (end_dt - start_dt).total_seconds() / 3600
            except ValueError:
                hours = 0.0

            if emp_id not in employee_hours:
                employee_hours[emp_id] = {"name": name, "role": role, "total_hours": 0.0, "shifts": 0}
            employee_hours[emp_id]["total_hours"] += hours
            employee_hours[emp_id]["shifts"] += 1

        # Build shift lines grouped by date
        shifts_by_date: Dict[str, List[str]] = {}
        for shift in sorted(shifts, key=lambda s: (s.get("shift_date", ""), s.get("start_time", ""))):
            d = shift.get("shift_date", "unknown")
            name = shift.get("employee_name") or shift.get("employee_id", "unknown")
            role = shift.get("role") or shift.get("notes") or "Unknown"
            line = f"  - {name} ({role}): {shift.get('start_time', '?')} – {shift.get('end_time', '?')}"
            shifts_by_date.setdefault(d, []).append(line)

        employee_summary = "\n".join(
            f"  - {v['name']} ({v['role']}): {v['total_hours']:.1f} hours across {v['shifts']} shift(s)"
            for v in employee_hours.values()
        ) or "  (no employees)"

        shifts_summary = "\n".join(
            f"\n{day}:\n" + "\n".join(lines)
            for day, lines in shifts_by_date.items()
        ) or "  (no shifts)"

        return (
            f"Week starting {week_start}\n\n"
            f"Employee summary:\n{employee_summary}\n\n"
            f"Shifts by day:{shifts_summary}"
        )


ai_service = AIService() if settings.ANTHROPIC_API_KEY else None
