-- One canonical, resumable research publication per local market date.
-- Score snapshots remain immutable; this ledger selects the one publication
-- the product is allowed to read after an interrupted or repeated update.

BEGIN;

CREATE TABLE quantrade.daily_research_runs (
    score_date DATE PRIMARY KEY,
    status TEXT NOT NULL CHECK (status IN ('running', 'completed', 'failed', 'skipped')),
    decision_at TIMESTAMPTZ,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ,
    score_snapshot_count INTEGER CHECK (score_snapshot_count >= 0),
    eligible_count INTEGER CHECK (eligible_count >= 0),
    failure_reason TEXT,
    CHECK (
        (status = 'completed'
         AND decision_at IS NOT NULL AND completed_at IS NOT NULL
         AND score_snapshot_count IS NOT NULL AND eligible_count IS NOT NULL
         AND failure_reason IS NULL)
        OR
        (status = 'skipped'
         AND completed_at IS NOT NULL AND failure_reason IS NOT NULL)
        OR
        (status IN ('running', 'failed'))
    )
);

CREATE INDEX daily_research_runs_completed_idx
    ON quantrade.daily_research_runs (score_date DESC)
    WHERE status = 'completed';

-- Preserve existing immutable score records and designate the latest complete
-- decision timestamp as the canonical historical publication for each date.
WITH latest_decisions AS (
    SELECT DISTINCT ON (score_date) score_date, decision_at
    FROM quantrade.score_snapshots
    ORDER BY score_date, decision_at DESC
), counts AS (
    SELECT score_date, decision_at,
           COUNT(*)::integer AS score_snapshot_count,
           COUNT(*) FILTER (WHERE eligible)::integer AS eligible_count,
           MAX(published_at) AS completed_at
    FROM quantrade.score_snapshots
    GROUP BY score_date, decision_at
)
INSERT INTO quantrade.daily_research_runs
    (score_date, status, decision_at, started_at, completed_at, score_snapshot_count, eligible_count)
SELECT counts.score_date, 'completed', counts.decision_at, counts.decision_at,
       COALESCE(counts.completed_at, counts.decision_at), counts.score_snapshot_count, counts.eligible_count
FROM counts
JOIN latest_decisions
  ON latest_decisions.score_date = counts.score_date
 AND latest_decisions.decision_at = counts.decision_at
ON CONFLICT (score_date) DO NOTHING;

COMMIT;
