import base64
import json
import logging
import re
from typing import Any, Dict, List, Optional

import groq

from ..core.config import settings

logger = logging.getLogger(__name__)

MODEL = "llama-3.3-70b-versatile"

_VISION_SYSTEM_PROMPT = """You are extracting a restaurant shift schedule from an image — a photo or screenshot of a handwritten or printed schedule table. Most schedules like this (whiteboards especially) show employee NAMES, not job roles — that's expected, not a gap.

Return ONLY valid JSON matching this exact schema — no markdown, no extra text:

{
  "shifts": [
    {
      "name": <string, the employee's name as written, or null if unclear>,
      "day_of_week": <int 1-7, 1=Monday...7=Sunday, or null if unclear>,
      "start_time": <string "HH:MM" or "HH:MM:SS", or null if unclear>,
      "end_time": <string "HH:MM" or "HH:MM:SS", or null if unclear>,
      "role": <string, or null>,
      "count": <int number of employees needed for this shift — use 1 unless the image explicitly groups multiple people under one row>
    }
  ]
}

Rules:
- One element per distinct shift you can identify in the image.
- Extract "name" whenever a person's name appears next to a shift — this is the primary identifier for most schedules and should be populated far more often than "role".
- Only set "role" when a role/position label is unambiguously present right next to the name or shift (e.g. "(Server)", a colored badge with a role name, an explicit "Role" column). Do NOT infer or guess a role from a name, context, or typical scheduling patterns — leave it null instead.
- If ANY other field is ambiguous, illegible, or you are not confident about it, use null for that field rather than guessing.
- Do not invent shifts that aren't visible in the image.
- Return {"shifts": []} if no shifts are identifiable."""

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

    def analyze_image_for_templates(
        self, image_bytes: bytes, mime_type: str = "image/jpeg"
    ) -> List[Dict[str, Any]]:
        """
        Extract candidate shift templates from a photo/screenshot of a schedule.

        All Groq-specific details (model choice, image encoding, message
        shape) live in this one method. Callers depend only on the
        (image bytes, mime_type) -> List[Dict] contract, so swapping the
        model (GROQ_VISION_MODEL) or the provider entirely later only touches
        this method — not the import/validation pipeline that consumes it.

        Args:
            image_bytes: Raw image content
            mime_type: Image MIME type (e.g. "image/jpeg", "image/png")

        Returns:
            List of raw shift dicts (name, day_of_week, start_time, end_time,
            role, count) — fields may be None where the model flagged
            uncertainty. `role` is null by default unless an explicit role
            label was visible; callers resolve it from `name` via the
            employee roster. Not yet validated; pass through
            validate_parsed_templates.

        Raises:
            ValueError: If the model's response can't be parsed into the
                        expected shape.
        """
        logger.info("Analysing schedule image (%d bytes, %s)", len(image_bytes), mime_type)

        b64_image = base64.b64encode(image_bytes).decode("utf-8")

        # NOTE: response_format={"type": "json_object"} is deliberately NOT set
        # here. On Groq's vision model, combining json_object mode with image
        # inputs intermittently returns an empty completion, which Groq then
        # rejects server-side as `json_validate_failed` with empty
        # `failed_generation` — surfacing as a 400 to us and a 502 to the
        # client. The system prompt already demands strict JSON; we strip any
        # accidental markdown fence and parse manually below, which is
        # strictly more forgiving.
        response = self._client.chat.completions.create(
            model=settings.GROQ_VISION_MODEL,
            messages=[
                {"role": "system", "content": _VISION_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            # /no_think is a qwen3 chat-template directive that
                            # suppresses the internal <think>…</think> reasoning
                            # trace. On ambiguous whiteboard photos the model
                            # was burning its entire output budget re-examining
                            # regions inside <think> and never emitting JSON;
                            # skipping reasoning routes the full max_tokens
                            # budget straight into the answer. Safe on
                            # non-reasoning models — they treat it as literal
                            # text and ignore it.
                            "text": "Extract every shift you can identify from this schedule image. Respond with JSON only, no prose. /no_think",
                        },
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{mime_type};base64,{b64_image}"},
                        },
                    ],
                },
            ],
            temperature=0.1,  # low temp — this is extraction, not generation
            # Groq counts max_tokens against the per-minute TPM cap upfront,
            # so this can't just be "generous". Free-tier TPM on qwen3.6-27b
            # is 8000; a downscaled schedule image runs ~2500-3000 input
            # tokens, so 4096 output leaves us at ~7k total — inside the cap
            # while still fitting ~60 shifts of JSON. If a restaurant hits
            # this ceiling in practice, the right fix is Groq Dev Tier
            # (much higher TPM), not shrinking output further.
            max_tokens=4096,
            # Belt-and-suspenders reasoning suppression alongside the
            # /no_think directive in the user message. Groq silently drops
            # unknown params, so this is safe if the field name changes;
            # extra_body dodges any SDK-level param typing.
            extra_body={"reasoning_effort": "none"},
        )

        raw = (response.choices[0].message.content or "").strip()
        if not raw:
            logger.error("Vision model returned an empty completion")
            raise ValueError("Vision model returned an empty response")

        raw = _extract_json_payload(raw)

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as e:
            # Log a tail slice too — truncation shows up at the end, not the
            # start. Head alone hid a max_tokens cutoff during debugging.
            logger.error(
                "Vision model returned invalid JSON: %s | head=%r | tail=%r | len=%d",
                e,
                raw[:300],
                raw[-300:],
                len(raw),
            )
            raise ValueError(f"Vision model returned malformed JSON: {e}") from e

        if isinstance(parsed, list):
            shifts = parsed
        elif isinstance(parsed, dict):
            shifts = parsed.get("shifts")
        else:
            shifts = None

        if not isinstance(shifts, list):
            raise ValueError("Vision model response missing a 'shifts' array")

        logger.info("Vision model identified %d candidate shift(s)", len(shifts))
        return shifts

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


def _extract_json_payload(text: str) -> str:
    """Return the JSON body from a raw model response.

    Handles three things vision/reasoning models routinely mix in around the
    actual JSON:
      1. A ```json … ``` (or bare ```) markdown fence.
      2. A leading <think>…</think> reasoning block (qwen3 and other
         reasoning models emit these when reasoning isn't suppressed).
      3. Arbitrary prose before/after the object.

    Strategy: strip fences, drop any <think> blocks, then slice from the first
    '{' to the last '}'. If no braces are found, return the stripped text and
    let json.loads raise — the caller logs the raw payload for debugging.
    """
    stripped = text.strip()

    if stripped.startswith("```"):
        stripped = stripped.removeprefix("```json").removeprefix("```").lstrip("\n")
        if stripped.endswith("```"):
            stripped = stripped[:-3]
        stripped = stripped.strip()

    stripped = re.sub(r"<think>.*?</think>", "", stripped, flags=re.DOTALL).strip()

    # Slice to the outermost JSON container — object or array — so any leading
    # apologies / trailing prose the model tacks on gets dropped.
    candidates = [
        (stripped.find(open_c), stripped.rfind(close_c))
        for open_c, close_c in (("{", "}"), ("[", "]"))
    ]
    valid = [(f, l) for f, l in candidates if f != -1 and l > f]
    if valid:
        first, last = min(valid, key=lambda fl: fl[0])
        return stripped[first : last + 1]
    return stripped


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
