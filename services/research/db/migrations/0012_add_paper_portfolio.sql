-- Private research-only paper portfolio, executed at the first regular-session open after a dated score run.

BEGIN;

CREATE TABLE quantrade.paper_portfolio_runs (
    paper_portfolio_run_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    score_date DATE NOT NULL UNIQUE,
    execution_date DATE NOT NULL CHECK (execution_date > score_date),
    starting_nav NUMERIC(20, 8) NOT NULL CHECK (starting_nav > 0),
    ending_cash NUMERIC(20, 8) NOT NULL CHECK (ending_cash >= 0),
    benchmark_ticker TEXT NOT NULL CHECK (benchmark_ticker ~ '^[A-Z][A-Z. -]{0,14}$'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE quantrade.paper_portfolio_positions (
    paper_portfolio_run_id UUID NOT NULL REFERENCES quantrade.paper_portfolio_runs(paper_portfolio_run_id),
    security_id UUID NOT NULL REFERENCES quantrade.securities(security_id),
    quantity NUMERIC(24, 12) NOT NULL CHECK (quantity > 0),
    PRIMARY KEY (paper_portfolio_run_id, security_id)
);

CREATE TABLE quantrade.paper_portfolio_trades (
    paper_portfolio_run_id UUID NOT NULL REFERENCES quantrade.paper_portfolio_runs(paper_portfolio_run_id),
    security_id UUID NOT NULL REFERENCES quantrade.securities(security_id),
    side TEXT NOT NULL CHECK (side IN ('buy', 'sell')),
    quantity NUMERIC(24, 12) NOT NULL CHECK (quantity > 0),
    execution_price NUMERIC(20, 8) NOT NULL CHECK (execution_price > 0),
    notional NUMERIC(20, 8) NOT NULL CHECK (notional > 0),
    PRIMARY KEY (paper_portfolio_run_id, security_id, side)
);

CREATE FUNCTION quantrade.prevent_paper_portfolio_mutation()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'paper portfolio records are immutable';
END;
$$;

CREATE TRIGGER paper_portfolio_runs_immutable
BEFORE UPDATE OR DELETE ON quantrade.paper_portfolio_runs
FOR EACH ROW EXECUTE FUNCTION quantrade.prevent_paper_portfolio_mutation();

CREATE TRIGGER paper_portfolio_positions_immutable
BEFORE UPDATE OR DELETE ON quantrade.paper_portfolio_positions
FOR EACH ROW EXECUTE FUNCTION quantrade.prevent_paper_portfolio_mutation();

CREATE TRIGGER paper_portfolio_trades_immutable
BEFORE UPDATE OR DELETE ON quantrade.paper_portfolio_trades
FOR EACH ROW EXECUTE FUNCTION quantrade.prevent_paper_portfolio_mutation();

COMMIT;
