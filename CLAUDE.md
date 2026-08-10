# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

ShiftCraft API is a restaurant scheduling backend built with FastAPI and Supabase. It manages employees, weekly schedules, and shifts — with an auto-generation algorithm that distributes hours fairly across staff.

## Commands

```bash
# Install dependencies (uses uv)
uv install

# Run development server with hot reload
uvicorn app.api.main:app --reload

# Run all tests
pytest

# Run a specific test file
pytest app/tests/test_employee_service.py

# Run a specific test function
pytest app/tests/test_root.py::test_root_endpoint -v

# Build and run with Docker Compose
docker-compose up -d
```

**Required `.env` variables:**
```
ENVIRONMENT=development
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your_anon_key_here
```

API docs available at `http://localhost:8000/docs` in development mode only.

## Architecture

```
HTTP Request
    ↓
app/api/routes/        ← Thin route handlers, minimal logic
    ↓
app/services/          ← All business logic lives here
    ↓
app/core/db.py         ← Supabase client
    ↓
PostgreSQL (via Supabase)
```

**Routes → Services mapping:**
- `employee_router.py` → `employee_service.py`
- `schedule_router.py` → `schedule_service.py` + `schedule_generator_service.py`
- `shift_router.py` → `shifts_service.py`

**Models (`app/models/`)** are pure Pydantic schemas for request/response validation — no ORM, all DB calls use raw Supabase client queries in the service layer.

**Constants (`app/core/constants.py`)** holds hardcoded restaurant config: operating hours (Tue–Sun, closed Mondays), 18 shift templates, and the `DayOfWeek` enum (ISO 8601: Monday=1, Sunday=7).

## Key Service Behaviors

**Schedule Generator (`schedule_generator_service.py`):**
- Generates a full week of shifts in under 1 second via bulk insert
- Priority order: coverage first, fairness second. Fills every shift template if any feasible
  assignment exists — a template is only left unfilled when every eligible employee would breach
  a hard constraint (hours cap, rest window, availability). Fairness (fewest hours so far) is the
  tiebreak among employees who are all feasible for a slot, not a reason to leave it empty.
- Slots are processed hardest-to-staff first (fewest role+availability-eligible candidates) so a
  scarce employee isn't consumed by an easy slot before a harder one only they can fill. This is
  a heuristic (provably optimal fill is NP-hard here), not a 100% guarantee.
- Re-running generation for a week that already has shifts tops up only the slots still missing
  (`_preload_existing_shifts` returns per-slot fill counts) — it does not duplicate shifts.
- Shift templates are deduplicated by (day_of_week, start_time, end_time, role) — both on save
  (`shift_template_service.upsert_templates`) and defensively again inside the generator — via
  `app/core/template_utils.dedupe_shift_templates`.
- Filters by role (Server, Cook, Manager) and active status
- Uses shift templates from `constants.py` which define day, times, role, and required headcount

**Shift Validation (`shifts_service.py`):**
- Validates overlap: same employee cannot have overlapping shifts on the same date
- Validates time bounds: `end_time > start_time`, max 10 hours per shift
- Validates employee is active and exists
- Validates shift date falls within the schedule's week
- Operating hours validation is not yet implemented (TODO)

**Schedule aggregation (`GET /schedules/{id}`):** Returns a schedule with all its shifts grouped and nested — this requires multiple Supabase queries joined in Python, not a DB join.

## Data Conventions

- Week start dates are always normalized to Monday (ISO 8601)
- Times stored as `HH:MM:SS` strings
- Dates stored as ISO format strings
- UUIDs are converted to strings for Supabase operations
- Employee deletion is split in two: `POST /employees/{id}/deactivate` soft-deletes (`is_active=False`) — this is the "Disable" action and the safe default for anyone who's worked a shift. `DELETE /employees/{id}` hard-deletes and is blocked with `409` if the employee has any shift history (`EmployeeHasShiftsError`); it does clean up the employee's `employee_availability` rows first, since those have no historical value.
