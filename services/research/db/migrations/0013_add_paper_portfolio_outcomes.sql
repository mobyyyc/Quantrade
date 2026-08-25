-- Immutable, horizon-specific observations for forward paper portfolios.

BEGIN;

CREATE TABLE quantrade.paper_portfolio_outcomes (
    paper_portfolio_run_id UUID NOT NULL REFERENCES quantrade.paper_portfolio_runs(paper_portfolio_run_id),
    horizon_sessions SMALLINT NOT NULL CHECK (horizon_sessions IN (5, 20, 60)),
    status TEXT NOT NULL CHECK (status IN ('completed', 'withheld')),
    outcome_date DATE NOT NULL CHECK (outcome_date >= DATE '2000-01-01'),
    portfolio_return NUMERIC(20, 12),
    benchmark_return NUMERIC(20, 12),
    benchmark_relative_return NUMERIC(20, 12),
    unavailable_reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (paper_portfolio_run_id, horizon_sessions),
    CHECK (
        (status = 'completed'
         AND portfolio_return IS NOT NULL
         AND benchmark_return IS NOT NULL
         AND benchmark_relative_return IS NOT NULL
         AND unavailable_reason IS NULL)
        OR
        (status = 'withheld'
         AND portfolio_return IS NULL
         AND benchmark_return IS NULL
         AND benchmark_relative_return IS NULL
         AND unavailable_reason IS NOT NULL)
    )
);

CREATE INDEX paper_portfolio_outcomes_outcome_date_idx
    ON quantrade.paper_portfolio_outcomes (outcome_date DESC);

CREATE TRIGGER paper_portfolio_outcomes_immutable
BEFORE UPDATE OR DELETE ON quantrade.paper_portfolio_outcomes
FOR EACH ROW EXECUTE FUNCTION quantrade.prevent_paper_portfolio_mutation();

COMMIT;
