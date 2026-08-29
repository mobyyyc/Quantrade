\set ON_ERROR_STOP on

-- Remove SEC filing metadata outside Quantrade's research form scope only
-- when no extracted fact or immutable observation depends on the filing.
-- Safe to repeat: a completed run leaves no eligible targets.

BEGIN;

SET LOCAL lock_timeout = '10s';
SET LOCAL statement_timeout = '10min';

-- Serialize with the daily research update before selecting deletion targets.
SELECT pg_advisory_xact_lock(7136202600824);

CREATE TEMP TABLE irrelevant_sec_filing_cleanup_targets (
    filing_id UUID PRIMARY KEY
) ON COMMIT DROP;

INSERT INTO irrelevant_sec_filing_cleanup_targets (filing_id)
SELECT filing.filing_id
FROM quantrade.filings AS filing
WHERE filing.form = 'other'
  AND NOT EXISTS (
      SELECT 1
      FROM quantrade.filing_facts AS fact
      WHERE fact.filing_id = filing.filing_id
  )
  AND NOT EXISTS (
      SELECT 1
      FROM quantrade.filing_fact_observations AS observation
      WHERE observation.filing_id = filing.filing_id
  );

SELECT COUNT(*) AS cleanup_target_count
FROM irrelevant_sec_filing_cleanup_targets;

WITH deleted AS (
    DELETE FROM quantrade.filings AS filing
    USING irrelevant_sec_filing_cleanup_targets AS target
    WHERE filing.filing_id = target.filing_id
    RETURNING filing.filing_id
)
SELECT COUNT(*) AS deleted_filing_count
FROM deleted;

COMMIT;

-- This maintenance operation is deliberately offline: reclaim the disk space
-- from the one-time historical cleanup instead of leaving reusable dead pages.
VACUUM (FULL, ANALYZE) quantrade.filings;

SELECT form, COUNT(*) AS retained_filing_count
FROM quantrade.filings
GROUP BY form
ORDER BY form;
