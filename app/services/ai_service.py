import json
import logging
from typing import Any, Dict, List, Optional

import groq

from ..core.config import settings

logger = logging.getLogger(__name__)

MODEL = "llama-3.3-70b-versatile"

_SYSTEM_PROMPT = """You are a restaurant scheduling expert. Analyze weekly staff schedules and return a structured JSON report that managers can act on immediately.

You will receive:
- The week start date
- The full employee roster (including those with zero shifts this week)
- A list of shifts grouped by date (employee name, role, start/end time)

Return ONLY valid JSON matching this exact schema — no markdown, no extra text:

{
  "summary": "<one sentence overview of the week>",
  "fairness": {
    "score": "<good|fair|poor>",
    "details": "<analysis of hour distribution within each role>"
  },
  "coverage": {
    "score": "<good|fair|poor>",
    "details": "<analysis of day/time slot coverage and any gaps>"
  },
  "workload": {
    "score": "<good|fair|poor>",
    "details": "<flag anyone with too many or too few hours, including employees with zero shifts>"
  },
  "patterns": [
    "<one notable scheduling pattern per item, e.g. back-to-back long shifts>"
  ],
  "recommendations": [
    "<one concrete, specific recommendation per item — max 3>"
  ]
}

Rules:
- Score "good" = no issues, "fair" = minor concerns, "poor" = needs attention
- Ground every observation in the actual data — no generic advice
- patterns and recommendations are arrays of strings (may be empty arrays if nothing to flag)
- Keep each string concise (1–2 sentences max)"""


class AIServiceUnavailableError(Exception):
    """Raised when the AI service cannot be reached or is not configured."""


class AIService:
    """Provides AI-powered schedule analysis using Groq (llama-3.3-70b-versatile)."""

    def __init__(self) -> None:
        if not settings.GROQ_API_KEY:
            raise AIServiceUnavailableError(
                "GROQ_API_KEY is not configured. Set it in your .env file."
            )
        self._client = groq.Groq(api_key=settings.GROQ_API_KEY)

    def analyze_schedule(
        self,
        schedule: Dict[str, Any],
        shifts: List[Dict[str, Any]],
        all_employees: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Analyse a weekly schedule and return a structured report.

        Args:
            schedule: The schedule record (id, restaurant_id, week_start, …)
            shifts: All shifts belonging to this schedule, with employee_name and role flattened on
            all_employees: Full active employee roster for the restaurant (optional).
                           When provided, the model can flag employees who got zero shifts.

        Returns:
            A dict matching the structured analysis schema.

        Raises:
            ValueError: If the model returns malformed JSON or a schema mismatch.
        """
        logger.info(
            "Analysing schedule id=%s week_start=%s shifts=%d",
            schedule.get("id"),
            schedule.get("week_start"),
            len(shifts),
        )

        prompt = self._build_analysis_prompt(schedule, shifts, all_employees or [])

        response = self._client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.3,  # low temp for consistent, factual output
            max_tokens=1024,
        )

        raw = response.choices[0].message.content.strip()

        try:
            result = json.loads(raw)
        except json.JSONDecodeError as e:
            logger.error("AI returned invalid JSON for schedule_id=%s: %s", schedule.get("id"), e)
            raise ValueError(f"AI returned malformed JSON: {e}") from e

        _validate_analysis_shape(result)

        logger.info("Schedule analysis complete for id=%s", schedule.get("id"))
        return result

    @staticmethod
    def _build_analysis_prompt(
        schedule: Dict[str, Any],
        shifts: List[Dict[str, Any]],
        all_employees: List[Dict[str, Any]],
    ) -> str:
        week_start = schedule.get("week_start", "unknown")

        # Per-employee hours from shifts this week
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
                hours = (
                    datetime.strptime(end_str, fmt) - datetime.strptime(start_str, fmt)
                ).total_seconds() / 3600
            except ValueError:
                hours = 0.0

            if emp_id not in employee_hours:
                employee_hours[emp_id] = {"name": name, "role": role, "total_hours": 0.0, "shifts": 0}
            employee_hours[emp_id]["total_hours"] += hours
            employee_hours[emp_id]["shifts"] += 1

        # Flag employees on the roster who have no shifts this week
        zero_shift_employees = []
        if all_employees:
            assigned_ids = set(employee_hours.keys())
            for emp in all_employees:
                if str(emp.get("id", "")) not in assigned_ids:
                    zero_shift_employees.append(
                        f"  - {emp.get('name', 'Unknown')} ({emp.get('role', 'Unknown')}): 0 hours, 0 shifts"
                    )

        # Shifts grouped by date
        shifts_by_date: Dict[str, List[str]] = {}
        for shift in sorted(shifts, key=lambda s: (s.get("shift_date", ""), s.get("start_time", ""))):
            d = shift.get("shift_date", "unknown")
            name = shift.get("employee_name") or shift.get("employee_id", "unknown")
            role = shift.get("role") or shift.get("notes") or "Unknown"
            line = f"  - {name} ({role}): {shift.get('start_time', '?')}–{shift.get('end_time', '?')}"
            shifts_by_date.setdefault(d, []).append(line)

        assigned_summary = (
            "\n".join(
                f"  - {v['name']} ({v['role']}): {v['total_hours']:.1f}h across {v['shifts']} shift(s)"
                for v in employee_hours.values()
            )
            or "  (none)"
        )

        unassigned_section = ""
        if zero_shift_employees:
            unassigned_section = (
                "\n\nEmployees with NO shifts this week:\n"
                + "\n".join(zero_shift_employees)
            )

        shifts_section = (
            "\n".join(
                f"\n{day}:\n" + "\n".join(lines)
                for day, lines in shifts_by_date.items()
            )
            or "  (no shifts scheduled)"
        )

        return (
            f"Week starting {week_start}\n\n"
            f"Assigned employees:\n{assigned_summary}"
            f"{unassigned_section}\n\n"
            f"Shifts by day:{shifts_section}"
        )


def _validate_analysis_shape(data: Dict[str, Any]) -> None:
    """Raise ValueError if the model response is missing required top-level keys."""
    required = {"summary", "fairness", "coverage", "workload", "patterns", "recommendations"}
    missing = required - data.keys()
    if missing:
        raise ValueError(f"AI response missing required fields: {missing}")

    for dim in ("fairness", "coverage", "workload"):
        block = data.get(dim, {})
        if not isinstance(block, dict) or "score" not in block or "details" not in block:
            raise ValueError(f"AI response has malformed '{dim}' field")
        if block["score"] not in ("good", "fair", "poor"):
            raise ValueError(f"Invalid score value in '{dim}': {block['score']!r}")

    if not isinstance(data.get("patterns"), list):
        raise ValueError("AI response 'patterns' must be a list")
    if not isinstance(data.get("recommendations"), list):
        raise ValueError("AI response 'recommendations' must be a list")


# Lazy singleton — only instantiated when first used, same pattern as all other services
_ai_service: Optional[AIService] = None


def get_ai_service() -> AIService:
    """Return the shared AIService instance, creating it on first call."""
    global _ai_service
    if _ai_service is None:
        _ai_service = AIService()
    return _ai_service
