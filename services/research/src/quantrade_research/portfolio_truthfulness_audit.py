"""Read-only integrity audit for official monthly paper portfolios."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
import json
from pathlib import Path

from .config import ConfigurationError, Settings
from .paper_portfolio import MONTHLY_FORMATION_PROTOCOL, _settings


@dataclass(frozen=True, slots=True)
class PortfolioAuditFinding:
    code: str
    severity: str
    detail: str
    formation_date: date | None = None


def audit_portfolio_truthfulness(*, settings: Settings) -> dict[str, object]:
    """Verify formation, execution, holdings, outcomes, gaps, and legacy previews."""
    if settings.database_url is None:
        raise ConfigurationError("DATABASE_URL is required for the portfolio audit")
    import psycopg

    findings: list[PortfolioAuditFinding] = []
    with psycopg.connect(settings.database_url) as connection, connection.cursor() as cursor:
        cursor.execute(
            """SELECT COUNT(*)
               FROM quantrade.paper_portfolio_runs
               WHERE formation_protocol <> %s""",
            (MONTHLY_FORMATION_PROTOCOL,),
        )
        legacy_count = int(cursor.fetchone()[0])
        if legacy_count:
            findings.append(PortfolioAuditFinding(
                "legacy_preview_excluded", "information",
                f"{legacy_count} legacy or preview portfolio record(s) remain stored but are excluded from official views.",
            ))

        cursor.execute(
            """SELECT portfolio.paper_portfolio_run_id::text, portfolio.score_date,
                      portfolio.execution_date, portfolio.starting_nav, portfolio.ending_cash,
                      portfolio.model_version,
                      (SELECT COUNT(*)
                       FROM quantrade.benchmark_daily_price_bars bar
                       WHERE bar.benchmark_ticker = portfolio.benchmark_ticker
                         AND bar.session = 'regular'
                         AND bar.adjustment_basis = 'unadjusted'
                         AND bar.session_date = portfolio.score_date) AS formation_session_count,
                      (SELECT MIN(bar.session_date)
                       FROM quantrade.benchmark_daily_price_bars bar
                       WHERE bar.benchmark_ticker = portfolio.benchmark_ticker
                         AND bar.session = 'regular'
                         AND bar.adjustment_basis = 'unadjusted'
                         AND bar.session_date > portfolio.score_date) AS expected_execution_date,
                      (SELECT COUNT(*) FROM quantrade.paper_portfolio_positions position
                       WHERE position.paper_portfolio_run_id = portfolio.paper_portfolio_run_id) AS position_count,
                      (SELECT COUNT(*) FROM quantrade.paper_portfolio_trades trade
                       WHERE trade.paper_portfolio_run_id = portfolio.paper_portfolio_run_id
                         AND trade.side = 'buy') AS buy_count,
                      (SELECT COALESCE(SUM(trade.notional), 0)
                       FROM quantrade.paper_portfolio_trades trade
                       WHERE trade.paper_portfolio_run_id = portfolio.paper_portfolio_run_id
                         AND trade.side = 'buy') AS buy_notional,
                      (SELECT COUNT(*)
                       FROM quantrade.paper_portfolio_positions position
                       JOIN quantrade.paper_portfolio_trades trade
                         ON trade.paper_portfolio_run_id = position.paper_portfolio_run_id
                        AND trade.security_id = position.security_id
                        AND trade.side = 'buy'
                       WHERE position.paper_portfolio_run_id = portfolio.paper_portfolio_run_id
                         AND (position.quantity <> trade.quantity
                              OR ABS(trade.notional - portfolio.starting_nav / 20) > 0.01))
                        AS invalid_ledger_row_count,
                      (SELECT COUNT(DISTINCT snapshot.model_version)
                       FROM quantrade.score_snapshots snapshot
                       JOIN quantrade.daily_research_runs run
                         ON run.score_date = snapshot.score_date
                        AND run.decision_at = snapshot.decision_at
                        AND run.status = 'completed'
                       WHERE snapshot.score_date = portfolio.score_date) AS formation_model_count,
                      (SELECT COUNT(*)
                       FROM quantrade.paper_portfolio_positions position
                       JOIN quantrade.score_snapshots snapshot
                         ON snapshot.security_id = position.security_id
                        AND snapshot.score_date = portfolio.score_date
                        AND snapshot.model_version = portfolio.model_version
                       JOIN quantrade.daily_research_runs run
                         ON run.score_date = snapshot.score_date
                        AND run.decision_at = snapshot.decision_at
                        AND run.status = 'completed'
                       WHERE position.paper_portfolio_run_id = portfolio.paper_portfolio_run_id
                         AND snapshot.eligible AND snapshot.rank <= 20) AS matching_top20_count
               FROM quantrade.paper_portfolio_runs portfolio
               WHERE portfolio.formation_protocol = %s
               ORDER BY portfolio.score_date""",
            (MONTHLY_FORMATION_PROTOCOL,),
        )
        official_rows = cursor.fetchall()
        for row in official_rows:
            (run_id, formation, execution, starting_nav, ending_cash, model_version,
             formation_session_count, expected_execution, position_count, buy_count, buy_notional,
             invalid_ledger_row_count,
             formation_model_count, matching_top20_count) = row
            prefix = f"Official portfolio {run_id}"
            if formation_session_count != 1:
                findings.append(PortfolioAuditFinding(
                    "invalid_formation_session", "critical",
                    f"{prefix} was not formed on a recorded regular SPY session.", formation,
                ))
            if expected_execution != execution:
                findings.append(PortfolioAuditFinding(
                    "invalid_next_open", "critical",
                    f"{prefix} does not use the first later regular SPY session.", formation,
                ))
            if (formation.year, formation.month) == (execution.year, execution.month):
                findings.append(PortfolioAuditFinding(
                    "not_month_end_formation", "critical",
                    f"{prefix} does not cross into a new calendar month.", formation,
                ))
            if not model_version or formation_model_count != 1:
                findings.append(PortfolioAuditFinding(
                    "ambiguous_formation_model", "critical",
                    f"{prefix} is not tied to one dated formation model.", formation,
                ))
            if (position_count != 20 or buy_count != 20 or matching_top20_count != 20
                    or invalid_ledger_row_count != 0):
                findings.append(PortfolioAuditFinding(
                    "invalid_holdings", "critical",
                    f"{prefix} does not preserve exactly the dated top 20 eligible holdings.", formation,
                ))
            if abs((buy_notional + ending_cash) - starting_nav) > start_tolerance(starting_nav):
                findings.append(PortfolioAuditFinding(
                    "formation_nav_mismatch", "critical",
                    f"{prefix} buy ledger and remaining cash do not reconcile to starting NAV.", formation,
                ))

        cursor.execute(
            """SELECT portfolio.score_date, outcome.horizon_sessions, outcome.status,
                      outcome.portfolio_return, outcome.benchmark_return,
                      outcome.benchmark_relative_return, outcome.accounting_rule,
                      outcome.portfolio_ledger_sha256, outcome.benchmark_ledger_sha256,
                      outcome.corporate_action_count, outcome.data_cutoff_at,
                      (SELECT session_date
                       FROM quantrade.benchmark_daily_price_bars bar
                       WHERE bar.benchmark_ticker = portfolio.benchmark_ticker
                         AND bar.session = 'regular'
                         AND bar.adjustment_basis = 'unadjusted'
                         AND bar.session_date >= portfolio.execution_date
                       ORDER BY bar.session_date
                       OFFSET outcome.horizon_sessions - 1 LIMIT 1) AS expected_outcome_date,
                      outcome.outcome_date
               FROM quantrade.paper_portfolio_runs portfolio
               JOIN quantrade.paper_portfolio_outcomes outcome
                 ON outcome.paper_portfolio_run_id = portfolio.paper_portfolio_run_id
               WHERE portfolio.formation_protocol = %s""",
            (MONTHLY_FORMATION_PROTOCOL,),
        )
        outcome_rows = cursor.fetchall()
        for row in outcome_rows:
            (formation, horizon, status, portfolio_return, benchmark_return, relative_return,
             accounting_rule, portfolio_hash, benchmark_hash, action_count, cutoff,
             expected_outcome, outcome_date) = row
            if expected_outcome != outcome_date:
                findings.append(PortfolioAuditFinding(
                    "invalid_outcome_window", "critical",
                    f"{horizon}-session outcome does not use its required market close.", formation,
                ))
            if status == "completed":
                complete_provenance = all(
                    value is not None
                    for value in (accounting_rule, portfolio_hash, benchmark_hash, action_count, cutoff)
                )
                arithmetic_matches = (
                    portfolio_return is not None and benchmark_return is not None
                    and relative_return is not None
                    and abs(relative_return - (portfolio_return - benchmark_return)) <= start_tolerance(1)
                )
                if not complete_provenance or not arithmetic_matches:
                    findings.append(PortfolioAuditFinding(
                        "invalid_completed_outcome", "critical",
                        f"{horizon}-session completed outcome lacks provenance or does not reconcile.", formation,
                    ))

        cursor.execute(
            """SELECT missed.formation_date
               FROM quantrade.missed_paper_portfolio_formations missed
               JOIN quantrade.paper_portfolio_runs portfolio
                 ON portfolio.score_date = missed.formation_date
                AND portfolio.formation_protocol = %s""",
            (MONTHLY_FORMATION_PROTOCOL,),
        )
        for (formation,) in cursor.fetchall():
            findings.append(PortfolioAuditFinding(
                "gap_conflicts_with_official_portfolio", "critical",
                "A formation is recorded as both missed and official.", formation,
            ))
        cursor.execute("SELECT COUNT(*) FROM quantrade.missed_paper_portfolio_formations")
        missed_count = int(cursor.fetchone()[0])

    critical_count = sum(item.severity == "critical" for item in findings)
    return {
        "status": "failed" if critical_count else "passed",
        "official_portfolio_count": len(official_rows),
        "outcome_count": len(outcome_rows),
        "missed_formation_count": missed_count,
        "legacy_preview_count": legacy_count,
        "critical_finding_count": critical_count,
        "findings": [
            {
                "code": item.code,
                "severity": item.severity,
                "detail": item.detail,
                **({"formation_date": item.formation_date.isoformat()} if item.formation_date else {}),
            }
            for item in findings
        ],
    }


def start_tolerance(value: object) -> Decimal:
    return max(abs(Decimal(value)) * Decimal("0.00000001"), Decimal("0.00000001"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit official monthly portfolio truthfulness")
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    report = audit_portfolio_truthfulness(settings=_settings(arguments.env_file))
    payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if arguments.output:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(payload, encoding="utf-8")
    print(payload, end="")
    if report["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
