import logging

from collections import defaultdict
from datetime import date, time, timedelta, datetime
from typing import List, Dict, Any, Optional, Tuple
from uuid import UUID, uuid4
from supabase import Client
from ..core.db import get_supabase
from .employee_service import EmployeeService
from .shifts_service import shifts_service
from .schedule_service import ScheduleService
from .shift_template_service import ShiftTemplateService

from ..core.constants import BELLAGIOS_SHIFT_TEMPLATES
from ..core.template_utils import dedupe_shift_templates

logger = logging.getLogger(__name__)

MIN_REST_HOURS = 10.0


class ScheduleGenerator:
    """
    Schedule Generator algorithm which handles shifts creation and assignment

    Priority order:
    1. Coverage: fill every shift template if any feasible assignment exists.
       A template is only left unfilled when every eligible employee would
       breach a hard constraint (hours cap, rest window, availability) — not
       merely because a "fairer" candidate wasn't available for that slot.
    2. Fairness: among employees who are all feasible for a given slot, the
       one with the fewest hours assigned so far gets it.

    To maximize coverage without a full constraint solver (provably optimal
    fill is NP-hard here — an employee's own shifts create sequencing
    dependencies via the rest-window constraint), slots are processed
    hardest-to-staff first (most-constrained-first): a scarce employee gets
    first claim on the one slot only they can fill, instead of being spent on
    an easy slot with many alternative candidates. This is a heuristic, not a
    guarantee — pathological inputs can still leave an avoidable gap — but it
    closes the vast majority of realistic cases.

    Re-running generation for a week that already has shifts tops up only
    the slots still missing (accounting for headcount already filled);
    duplicate shift templates (day/time/role) are deduplicated on the way in.

    Constraints enforced:
    - Minimum rest between shifts: 10 hours
    - Weekly hours cap: respects employee.max_hours_per_week when set

    shift_templates: List of shift patterns to create
                Example: [
                    {
                        "day_of_week": 1,  # Monday
                        "start_time": "09:00:00",
                        "end_time": "17:00:00",
                        "role": "Server",
                        "count": 2  # Need 2 servers
                    }
                ]
    """

    def __init__(self, supabase_client: Optional[Client] = None):
        self._supabase = supabase_client
        self._schedule_service: Optional[ScheduleService] = None
        self._employee_service: Optional[EmployeeService] = None
        self._shift_template_service: Optional[ShiftTemplateService] = None
        self.shift_service = shifts_service

    @property
    def supabase(self) -> Client:
        if self._supabase is None:
            self._supabase = get_supabase()
        return self._supabase

    @property
    def schedule_service(self) -> ScheduleService:
        if self._schedule_service is None:
            self._schedule_service = ScheduleService(self.supabase)
        return self._schedule_service

    @schedule_service.setter
    def schedule_service(self, value: ScheduleService) -> None:
        self._schedule_service = value

    @property
    def employee_service(self) -> EmployeeService:
        if self._employee_service is None:
            self._employee_service = EmployeeService(self.supabase)
        return self._employee_service

    @employee_service.setter
    def employee_service(self, value: EmployeeService) -> None:
        self._employee_service = value

    @property
    def shift_template_service(self) -> ShiftTemplateService:
        if self._shift_template_service is None:
            self._shift_template_service = ShiftTemplateService(self.supabase)
        return self._shift_template_service

    @shift_template_service.setter
    def shift_template_service(self, value: ShiftTemplateService) -> None:
        self._shift_template_service = value

    def generate_schedule(
        self,
        restaurant_id: UUID,
        week_start: date,
        shift_templates: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Generate a schedule for a given restaurant and week.

        Template resolution order:
            1. Explicitly passed shift_templates argument
            2. Saved templates in the database for this restaurant
            3. Hardcoded BELLAGIOS_SHIFT_TEMPLATES constant (fallback)

        Args:
            restaurant_id: Restaurant ID
            week_start: Monday of the week to generate
            shift_templates: Override templates (optional)
        """
        logger.info(
            "Generating schedule: restaurant_id=%s week_start=%s", restaurant_id, week_start
        )

        if shift_templates is None:
            saved = self.shift_template_service.get_templates(str(restaurant_id))
            if saved:
                shift_templates = saved["templates"]
                logger.info(
                    "Using %d saved shift templates for restaurant_id=%s",
                    len(shift_templates),
                    restaurant_id,
                )
            else:
                shift_templates = BELLAGIOS_SHIFT_TEMPLATES
                logger.info(
                    "No saved templates found, using default BELLAGIOS templates (%d)",
                    len(BELLAGIOS_SHIFT_TEMPLATES),
                )

        # Defensive dedup even for saved templates (already deduped on save) —
        # protects against data saved before that fix shipped, or a caller
        # passing a raw shift_templates override with accidental duplicates.
        shift_templates = dedupe_shift_templates(shift_templates)

        normalized_week_start = self.schedule_service.get_week_start(week_start)
        existing_schedule = self.schedule_service.get_schedule_by_week(
            normalized_week_start, str(restaurant_id)
        )

        if existing_schedule:
            logger.info(
                "Schedule already exists for week %s, appending shifts to id=%s",
                normalized_week_start,
                existing_schedule["id"],
            )
            schedule = existing_schedule
        else:
            schedule = self.schedule_service.create_schedule(restaurant_id, week_start)

        employees = self.employee_service.get_employees(restaurant_id, is_active=True)

        if not employees:
            raise ValueError("No active employees found")

        logger.info("Loaded %d active employees", len(employees))

        employees_by_role = defaultdict(list)
        for employee in employees:
            employees_by_role[employee["role"]].append(employee)

        employee_hours: Dict[str, float] = {emp["id"]: 0.0 for emp in employees}
        # All of an employee's assigned shift (start, end) intervals — not just
        # the most recent one. Slots are processed hardest-to-staff first, not
        # strictly in date order, so a chronologically-later shift can be
        # assigned before an earlier one for the same employee; rest must be
        # checked against every interval, on whichever side of it a new shift
        # falls, or an earlier shift can be wrongly rejected against a "gap"
        # computed the wrong direction.
        employee_shift_intervals: Dict[str, List[Tuple[datetime, datetime]]] = {
            emp["id"]: [] for emp in employees
        }

        # When appending to an existing schedule, preload already-assigned hours,
        # shift intervals, and per-slot fill counts so constraints apply across
        # both old and new shifts, and regeneration tops up rather than
        # duplicates already-filled slots.
        filled_slot_counts: Dict[tuple, int] = {}
        if existing_schedule:
            filled_slot_counts = self._preload_existing_shifts(
                schedule["id"], employee_hours, employee_shift_intervals
            )

        # Load availability once — { employee_id: { day_of_week: [(start, end), ...] } }
        availability_map = self._load_availability(str(restaurant_id))

        # Load time-off for the whole week in one query — { employee_id: set(date) }.
        # Treated as hard-unavailable: overlap with a shift_date removes the
        # employee from that slot's candidate pool, same as a missing
        # availability window would.
        time_off_dates = self._load_time_off(
            str(restaurant_id), week_start, week_start + timedelta(days=6)
        )

        # Build one flat task per still-needed headcount unit, then sort
        # hardest-to-staff first (fewest role+availability-eligible candidates)
        # so a scarce employee gets first claim on the slot only they can
        # fill, instead of being consumed by an easy slot with many
        # alternatives. See class docstring for why this isn't a full solver.
        slot_tasks = []

        for template in shift_templates:
            day_of_week = template["day_of_week"]
            start_time = self.parse_time(template["start_time"])
            end_time = self.parse_time(template["end_time"])
            role = template["role"]
            count = template.get("count", 1)

            shift_date = week_start + timedelta(days=day_of_week - 1)

            if not (week_start <= shift_date < week_start + timedelta(days=7)):
                continue

            eligible_employees = employees_by_role.get(role, [])

            if not eligible_employees:
                logger.warning(
                    "No employees with role '%s' available for template on %s",
                    role,
                    shift_date,
                )
                continue

            slot_key = (
                shift_date.isoformat(),
                start_time.isoformat(),
                end_time.isoformat(),
                role,
            )
            remaining = max(0, count - filled_slot_counts.get(slot_key, 0))
            if remaining == 0:
                continue

            duration = self.calculate_duration(start_time, end_time)
            scarcity = self._scarcity_score(
                role, day_of_week, start_time, end_time, employees_by_role, availability_map
            )

            for _ in range(remaining):
                slot_tasks.append(
                    {
                        "role": role,
                        "day_of_week": day_of_week,
                        "shift_date": shift_date,
                        "start_time": start_time,
                        "end_time": end_time,
                        "duration": duration,
                        "eligible_employees": eligible_employees,
                        "scarcity": scarcity,
                    }
                )

        slot_tasks.sort(key=lambda t: (t["scarcity"], t["shift_date"], t["start_time"]))

        created_shifts = []

        for task in slot_tasks:
            role = task["role"]
            day_of_week = task["day_of_week"]
            shift_date = task["shift_date"]
            start_time = task["start_time"]
            end_time = task["end_time"]
            duration = task["duration"]

            shift_start_dt = datetime.combine(shift_date, start_time)
            shift_end_dt = datetime.combine(shift_date, end_time)

            available = [
                emp for emp in task["eligible_employees"]
                if shift_date not in time_off_dates.get(emp["id"], set())
                and self._has_sufficient_rest(
                    employee_shift_intervals[emp["id"]], shift_start_dt, shift_end_dt
                )
                and not self._would_exceed_hours_cap(
                    emp, employee_hours[emp["id"]], duration
                )
                and self._is_available(
                    emp["id"], day_of_week, start_time, end_time, availability_map
                )
            ]

            if not available:
                logger.warning(
                    "No available employees for role '%s' on %s (rest/cap/availability constraints)",
                    role,
                    shift_date,
                )
                continue

            employee = self.select_employee_with_least_hours(available, employee_hours)

            logger.info(
                "Assigning %s: selected %s (current hours: %.1f)",
                role,
                employee.get("name"),
                employee_hours[employee["id"]],
            )

            shift_data = {
                "id": str(uuid4()),
                "schedule_id": str(schedule["id"]),
                "employee_id": str(employee["id"]),
                "shift_date": shift_date.isoformat(),
                "start_time": start_time.isoformat(),
                "end_time": end_time.isoformat(),
                "notes": f"{role}",
                "created_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat(),
            }

            created_shifts.append(shift_data)

            employee_hours[employee["id"]] += duration
            employee_shift_intervals[employee["id"]].append((shift_start_dt, shift_end_dt))

        if created_shifts:
            self.supabase.table("shifts").insert(created_shifts).execute()

        logger.info("Schedule generated: %d total shifts", len(created_shifts))

        return {
            "id": schedule["id"],
            "restaurant_id": schedule["restaurant_id"],
            "week_start": schedule["week_start"],
            "total_shifts": len(created_shifts),
            "status": "Completed",
        }

    def _load_time_off(
        self, restaurant_id: str, week_start: date, week_end: date
    ) -> Dict[str, set]:
        """
        Return { employee_id: set(date) } — every date in the given week
        that is covered by at least one time-off row for the restaurant.

        We expand ranges to a set of dates once here rather than doing an
        overlap check per (employee, slot) — the generator processes many
        slots per employee, so expanding once is cheaper. Weeks are 7 days,
        so the sets stay tiny.
        """
        # Local import avoids a circular dependency (time_off_service imports
        # employee_service, which the generator already touches at import).
        from .time_off_service import TimeOffService

        service = TimeOffService(self.supabase)
        rows = service.list_overlapping(restaurant_id, week_start, week_end)

        result: Dict[str, set] = {}
        for row in rows:
            emp_id = row["employee_id"]
            row_start = date.fromisoformat(row["start_date"])
            row_end = date.fromisoformat(row["end_date"])
            # Clamp the time-off range to the week window before expanding.
            span_start = max(row_start, week_start)
            span_end = min(row_end, week_end)
            dates = result.setdefault(emp_id, set())
            cursor = span_start
            while cursor <= span_end:
                dates.add(cursor)
                cursor += timedelta(days=1)

        if result:
            logger.info(
                "Loaded time-off for %d employees in week %s..%s",
                len(result),
                week_start,
                week_end,
            )
        return result

    def _load_availability(
        self, restaurant_id: str
    ) -> Dict[str, Dict[int, List[tuple]]]:
        """
        Load all availability windows for active employees in the restaurant.

        Returns a nested dict:
            { employee_id: { day_of_week: [(start_time, end_time), ...] } }

        Employees with no rows are absent from the map — the caller treats that
        as "no preference set, available for everything".
        """
        response = (
            self.supabase.table("employee_availability")
            .select("employee_id, day_of_week, start_time, end_time")
            .eq("restaurant_id", restaurant_id)
            .execute()
        )

        availability_map: Dict[str, Dict[int, List[tuple]]] = {}
        for row in response.data:
            emp_id = row["employee_id"]
            day = row["day_of_week"]
            window = (
                self.parse_time(row["start_time"]),
                self.parse_time(row["end_time"]),
            )
            availability_map.setdefault(emp_id, {}).setdefault(day, []).append(window)

        logger.info(
            "Loaded availability for %d employees (restaurant_id=%s)",
            len(availability_map),
            restaurant_id,
        )
        return availability_map

    @staticmethod
    def _is_available(
        employee_id: str,
        day_of_week: int,
        shift_start: time,
        shift_end: time,
        availability_map: Dict[str, Dict[int, List[tuple]]],
    ) -> bool:
        """
        Return True if the employee is available for the full shift window.

        Rules:
        - Employee not in map → no availability set → available for all shifts.
        - Employee in map but no entry for this day → unavailable that day.
        - Employee has entries for this day → at least one window must fully
          cover the shift (window.start <= shift.start AND window.end >= shift.end).
        """
        if employee_id not in availability_map:
            return True

        day_windows = availability_map[employee_id].get(day_of_week)
        if not day_windows:
            return False

        return any(
            avail_start <= shift_start and avail_end >= shift_end
            for avail_start, avail_end in day_windows
        )

    @classmethod
    def _scarcity_score(
        cls,
        role: str,
        day_of_week: int,
        start_time: time,
        end_time: time,
        employees_by_role: Dict[str, List[Dict[str, Any]]],
        availability_map: Dict[str, Dict[int, List[tuple]]],
    ) -> int:
        """
        Static (pre-assignment) count of employees who could plausibly fill a
        slot: right role and available that day/time. Deliberately ignores
        rest and hours-cap, since those evolve during assignment and aren't
        known yet — this is only used to decide processing ORDER (hardest
        slots first), not final eligibility.
        """
        eligible = employees_by_role.get(role, [])
        return sum(
            1
            for emp in eligible
            if cls._is_available(emp["id"], day_of_week, start_time, end_time, availability_map)
        )

    def _preload_existing_shifts(
        self,
        schedule_id: str,
        employee_hours: Dict[str, float],
        employee_shift_intervals: Dict[str, List[Tuple[datetime, datetime]]],
    ) -> Dict[Tuple[str, str, str, str], int]:
        """
        Load existing shifts for a schedule into the tracking dicts so that
        rest and hours-cap constraints apply correctly when appending new shifts.

        Also returns filled_slot_counts — how many shifts already exist per
        (shift_date, start_time, end_time, role) slot — so the caller can top
        up only what's still missing rather than re-creating shifts that
        already exist. Role is read from the shift's `notes` field (this
        generator writes notes=role at creation time); if a manager has since
        edited notes on a shift, that slot's count may be undercounted, which
        risks a slight over-fill rather than a hard failure.
        """
        filled_slot_counts: Dict[Tuple[str, str, str, str], int] = defaultdict(int)

        response = (
            self.supabase.table("shifts")
            .select("*")
            .eq("schedule_id", str(schedule_id))
            .execute()
        )
        for shift in response.data:
            role = shift.get("notes") or ""
            slot_key = (shift["shift_date"], shift["start_time"], shift["end_time"], role)
            filled_slot_counts[slot_key] += 1

            emp_id = shift["employee_id"]
            if emp_id not in employee_hours:
                continue
            start = self.parse_time(shift["start_time"])
            end = self.parse_time(shift["end_time"])
            duration = self.calculate_duration(start, end)
            employee_hours[emp_id] = employee_hours.get(emp_id, 0.0) + duration

            shift_date = date.fromisoformat(shift["shift_date"])
            start_dt = datetime.combine(shift_date, start)
            end_dt = datetime.combine(shift_date, end)
            employee_shift_intervals.setdefault(emp_id, []).append((start_dt, end_dt))

        logger.info("Preloaded existing shifts for schedule_id=%s", schedule_id)
        return dict(filled_slot_counts)

    @staticmethod
    def _has_sufficient_rest(
        existing_intervals: List[Tuple[datetime, datetime]],
        new_start: datetime,
        new_end: datetime,
    ) -> bool:
        """
        Return True if the new shift has at least MIN_REST_HOURS of rest from
        every one of the employee's other assigned shifts, on whichever side
        of it they fall.

        Checking against every interval (not just the chronologically-last
        one) matters because slots are processed hardest-to-staff first, not
        strictly in date order — a chronologically-later shift can be
        assigned before an earlier one for the same employee, and comparing
        only against "the last one assigned" would compute a nonsensical
        (negative) gap for an earlier shift that's actually well separated.
        """
        for existing_start, existing_end in existing_intervals:
            gap_after = (new_start - existing_end).total_seconds() / 3600
            gap_before = (existing_start - new_end).total_seconds() / 3600
            if gap_after >= MIN_REST_HOURS or gap_before >= MIN_REST_HOURS:
                continue
            return False
        return True

    @staticmethod
    def _would_exceed_hours_cap(
        employee: Dict[str, Any], current_hours: float, additional_hours: float
    ) -> bool:
        """Return True if adding this shift would exceed the employee's weekly hours cap."""
        cap = employee.get("max_hours_per_week")
        if cap is None:
            return False
        return current_hours + additional_hours > cap

    @staticmethod
    def select_employee_with_least_hours(
        employees: List[Dict], employee_hours: Dict[str, float]
    ) -> Optional[Dict]:
        """
        Select employee with fewest hours assigned.

        This ensures fair distribution of work.
        """
        if not employees:
            return None

        return min(employees, key=lambda e: employee_hours[e["id"]])

    @staticmethod
    def parse_time(time_str: str) -> time:
        """Parse time string to time object."""
        return datetime.strptime(time_str, "%H:%M:%S").time()

    @staticmethod
    def calculate_duration(start_time: time, end_time: time) -> float:
        """Calculate duration in hours."""
        start_dt = datetime.combine(date.today(), start_time)
        end_dt = datetime.combine(date.today(), end_time)
        return (end_dt - start_dt).total_seconds() / 3600


schedule_generator = ScheduleGenerator()
