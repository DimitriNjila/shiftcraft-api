-- Per-restaurant custom roles. Previously roles were constrained to the
-- Server/Cook/Manager enum in app/core/constants.py; owners can now define
-- their own set at onboarding (Barista, Host, Dishwasher, etc.) and the
-- employee create/update path validates role against this list.
--
-- Defaults to the historical enum so existing restaurants keep working
-- without a data backfill.
ALTER TABLE restaurants
ADD COLUMN roles TEXT[] NOT NULL DEFAULT ARRAY['Server', 'Cook', 'Manager'];
