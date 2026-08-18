-- Employee time-off requests. Semantically distinct from employee_availability
-- (which is a recurring weekly pattern like "I can work Mon-Wed evenings"):
-- a time_off row is a specific, dated absence like "out Fri 2026-08-21 for an
-- interview". The schedule generator treats any overlap between a shift date
-- and a time_off (start_date, end_date) range as hard-unavailable — same
-- treatment as a missing availability window.
CREATE TABLE time_off (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    employee_id    UUID NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
    restaurant_id  UUID NOT NULL REFERENCES restaurants(id) ON DELETE CASCADE,
    start_date     DATE NOT NULL,
    end_date       DATE NOT NULL,
    reason         TEXT,
    created_at     TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    updated_at     TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    CONSTRAINT time_off_date_order CHECK (end_date >= start_date)
);

-- Generator queries time_off by employee + date range on every schedule
-- generation; this covers both the "load all for a restaurant's week" scan
-- and the per-employee list endpoint.
CREATE INDEX idx_time_off_employee_dates ON time_off(employee_id, start_date, end_date);
CREATE INDEX idx_time_off_restaurant_dates ON time_off(restaurant_id, start_date, end_date);
