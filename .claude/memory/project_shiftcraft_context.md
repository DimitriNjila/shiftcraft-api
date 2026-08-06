---
name: ShiftCraft API — project context and recent work
description: Core architecture, design decisions, and features built so far in ShiftCraft API
type: project
---

ShiftCraft is a restaurant scheduling backend (FastAPI + Supabase/PostgreSQL), deployed on Vercel with separate staging (dev branch) and production (main branch) environments.

**Why:** Multi-tenant restaurant SaaS. All tables that involve tenant data must include `restaurant_id` — learned this the hard way from a multi-tenancy bug with the `schedules` UNIQUE constraint.

**How to apply:** Always include `restaurant_id` on any new table that is scoped to a restaurant. Never look up tenant data without filtering by `restaurant_id`.

## Architecture

```
app/
├── api/routes/         ← Thin route handlers
├── services/           ← All business logic
├── models/             ← Pydantic schemas (no ORM)
├── core/
│   ├── config.py       ← Pydantic Settings, lazy via get_settings()
│   ├── db.py           ← Lazy Supabase client via get_supabase()
│   └── constants.py    ← DayOfWeek enum (ISO 8601: Mon=1, Sun=7), BELLAGIOS_SHIFT_TEMPLATES
```

Services use lazy singleton pattern — module-level instance, only instantiated when first used (not at import time — avoids Vercel cold-start issues).

## Features built in this session (2026-06-20 to 2026-06-26)

### 1. Employee Availability (complete)
- **Table:** `employee_availability` (id, employee_id, restaurant_id, day_of_week 1–7, start_time, end_time)
- **Semantics:** No rows = no preference = always available. Rows on some days but not others = unavailable on unset days. Window must fully cover the shift (avail.start <= shift.start AND avail.end >= shift.end).
- **Service:** `app/services/availability_service.py` — get, add, delete windows
- **Endpoints:** nested under `/api/v1/employees/{id}/availability` in `employee_router.py`
- **Generator integration:** `_load_availability()` runs one query before the template loop, builds `{employee_id: {day_of_week: [(start, end)]}}`. `_is_available()` is a pure static check added to the `available` filter alongside rest/cap checks.
- **Tests:** `app/tests/test_availability_service.py` (13 tests) + additions to `test_schedule_generator_service.py` (16 new tests)
- **Migration SQL still needed in Supabase** (user has it — was provided in session)

### 2. AI Schedule Analysis — rewritten (complete)
- **Old:** Anthropic claude-opus-4-6, returned plain text blob, broken `thinking` param, new client per request
- **New:** Groq API + `llama-3.3-70b-versatile` (free, open-source). Structured JSON output with Pydantic validation. Lazy singleton via `get_ai_service()`. Richer prompt includes employees with zero shifts.
- **Response shape:**
  ```
  summary: str
  fairness/coverage/workload: { score: "good"|"fair"|"poor", details: str }
  patterns: list[str]
  recommendations: list[str]
  ```
- **Config:** `GROQ_API_KEY` (replaced `ANTHROPIC_API_KEY`)
- **Tests:** `app/tests/test_ai_service.py` fully rewritten (22 tests)
- **Frontend:** handoff prompt was provided; frontend agent needs to update the analysis UI to render score cards, patterns list, recommendations list instead of plain text

## Pending frontend work (handoff prompts were written for both)
1. **Availability UI** — weekly grid on employee detail page, chips per day, add/delete windows via API
2. **AI analysis UI** — replace text blob with score cards (good/fair/poor badges), patterns bullets, recommendations list
