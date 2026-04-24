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
- Fair distribution: assigns shifts to the employee with the fewest hours so far
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
- Employee deletion is a soft delete (sets `is_active=False`), not a hard delete
