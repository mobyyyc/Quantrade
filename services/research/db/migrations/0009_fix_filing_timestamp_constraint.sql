-- SEC acceptance timestamps occur after the filing date. The original core
-- schema accidentally enforced the reverse relationship.

BEGIN;

ALTER TABLE quantrade.filings
    DROP CONSTRAINT IF EXISTS filings_check1;

COMMIT;
