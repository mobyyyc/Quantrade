"""Run one locked, canonical private research publication after market close."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import date, datetime, timedelta
import os
from pathlib import Path
import subprocess
import sys
from typing import Iterator

from .forward_outcomes import materialize_due_forward_score_outcomes
from .paper_portfolio import publish_due_paper_portfolios
from .portfolio_outcomes import materialize_due_paper_portfolio_outcomes
from .score_run import TORONTO, _dotenv_values, _settings
from .universe_symbols import canonical_ticker


_LOCK_KEY = 7_136_202_600_824


def _symbols(database_url: str, score_date: date) -> list[str]:
    import psycopg
    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute("""SELECT m.security_id::text, l.ticker FROM quantrade.universe_snapshots u
                          JOIN quantrade.universe_memberships m ON m.universe_snapshot_id = u.universe_snapshot_id
                          JOIN quantrade.listings l ON l.security_id = m.security_id
                          WHERE u.universe_code = 'sp500' AND u.as_of_date <= %s AND l.valid_to IS NULL
                          ORDER BY u.as_of_date DESC, m.security_id, l.ticker""", (score_date,))
        candidates: dict[str, list[str]] = {}
        for security_id, ticker in cursor.fetchall():
            candidates.setdefault(str(security_id), []).append(str(ticker))
    return sorted(canonical_ticker(tickers) for tickers in candidates.values())


def _ciks(database_url: str, score_date: date) -> list[str]:
    import psycopg
    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute("""SELECT DISTINCT identifier.identifier_value
                          FROM quantrade.universe_snapshots universe
                          JOIN quantrade.universe_memberships membership
                            ON membership.universe_snapshot_id = universe.universe_snapshot_id
                          JOIN quantrade.security_identifiers identifier
                            ON identifier.security_id = membership.security_id
                           AND identifier.identifier_type = 'cik'
                           AND identifier.valid_from <= %s
                           AND (identifier.valid_to IS NULL OR identifier.valid_to > %s)
                          WHERE universe.universe_code = 'sp500' AND universe.as_of_date <= %s
                          ORDER BY identifier.identifier_value""", (score_date, score_date, score_date))
        return [str(row[0]).zfill(10) for row in cursor.fetchall()]


def _catch_up_start(database_url: str, score_date: date) -> date:
    """Fetch skipped market sessions too; they may still complete future labels.

    Scores are deliberately not backfilled: bars retrieved late cannot truthfully
    satisfy a prior score's point-in-time availability cutoff.
    """
    import psycopg
    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute("""SELECT MAX(session_date)
                          FROM quantrade.benchmark_daily_price_bars
                          WHERE benchmark_ticker = 'SPY' AND session = 'regular'
                            AND adjustment_basis = 'split_adjusted'""")
        latest = cursor.fetchone()[0]
    return score_date if latest is None else min(score_date, latest + timedelta(days=1))


@contextmanager
def _daily_update_lock(database_url: str) -> Iterator[object]:
    """Hold a PostgreSQL advisory lock across all ingestion and scoring work."""
    import psycopg
    connection = psycopg.connect(database_url, autocommit=True)
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_try_advisory_lock(%s)", (_LOCK_KEY,))
            if not cursor.fetchone()[0]:
                raise RuntimeError("A daily research update is already running.")
        yield connection
    finally:
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_unlock(%s)", (_LOCK_KEY,))
        connection.close()


def _run_row(connection, score_date: date) -> tuple[str, datetime | None] | None:
    with connection.cursor() as cursor:
        cursor.execute("SELECT status, decision_at FROM quantrade.daily_research_runs WHERE score_date = %s", (score_date,))
        row = cursor.fetchone()
    return (str(row[0]), row[1]) if row else None


def _start_or_resume(connection, score_date: date) -> tuple[bool, datetime | None]:
    """Return whether work is needed plus a fixed retry cutoff, when one exists."""
    existing = _run_row(connection, score_date)
    if existing and existing[0] == "completed":
        return False, existing[1]
    with connection.cursor() as cursor:
        cursor.execute(
            """INSERT INTO quantrade.daily_research_runs (score_date, status, started_at)
               VALUES (%s, 'running', now())
               ON CONFLICT (score_date) DO UPDATE
               SET status = 'running', started_at = EXCLUDED.started_at, completed_at = NULL,
                   score_snapshot_count = NULL, eligible_count = NULL, failure_reason = NULL""",
            (score_date,),
        )
    return True, existing[1] if existing else None


def _set_failure(connection, score_date: date, reason: str) -> None:
    with connection.cursor() as cursor:
        cursor.execute("""UPDATE quantrade.daily_research_runs
                          SET status = 'failed', completed_at = now(), failure_reason = %s
                          WHERE score_date = %s""", (reason[:2000], score_date))


def _set_skipped(connection, score_date: date, reason: str) -> None:
    with connection.cursor() as cursor:
        cursor.execute("""UPDATE quantrade.daily_research_runs
                          SET status = 'skipped', completed_at = now(), failure_reason = %s
                          WHERE score_date = %s""", (reason, score_date))


def _set_decision_at(connection, score_date: date, existing: datetime | None) -> datetime:
    decision_at = existing or datetime.now(TORONTO)
    with connection.cursor() as cursor:
        cursor.execute("UPDATE quantrade.daily_research_runs SET decision_at = %s WHERE score_date = %s", (decision_at, score_date))
    return decision_at


def _set_completed(connection, score_date: date, snapshots: int, eligible: int) -> None:
    with connection.cursor() as cursor:
        cursor.execute("""UPDATE quantrade.daily_research_runs
                          SET status = 'completed', completed_at = now(), score_snapshot_count = %s,
                              eligible_count = %s, failure_reason = NULL
                          WHERE score_date = %s""", (snapshots, eligible, score_date))


def _has_current_benchmark_session(database_url: str, score_date: date) -> bool:
    import psycopg
    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute("""SELECT EXISTS (
                            SELECT 1 FROM quantrade.benchmark_daily_price_bars
                            WHERE benchmark_ticker = 'SPY' AND session = 'regular'
                              AND adjustment_basis = 'split_adjusted' AND session_date = %s
                        )""", (score_date,))
        return bool(cursor.fetchone()[0])


def _published_score_summary(
    database_url: str, score_date: date, expected_count: int,
) -> tuple[datetime, int, int] | None:
    """Find a complete canonical snapshot set after a later daily-update step fails.

    Snapshot evidence is authoritative: a failed ledger row may be retried or
    repaired, but an immutable completed score set retains its own decision time.
    """
    import psycopg
    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute(
            """SELECT decision_at, COUNT(*), COUNT(*) FILTER (WHERE eligible)
               FROM quantrade.score_snapshots
               WHERE score_date = %s
               GROUP BY decision_at
               HAVING COUNT(*) = %s
               ORDER BY decision_at DESC
               LIMIT 1""",
            (score_date, expected_count),
        )
        row = cursor.fetchone()
    if row is None:
        return None
    return row[0], int(row[1]), int(row[2])


def _run(command: list[str], environment: dict[str, str]) -> str:
    completed = subprocess.run(command, env=environment, check=True, text=True, capture_output=True)
    return completed.stdout.strip()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the private daily Quantrade update once per market date")
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    arguments = parser.parse_args()
    settings = _settings(arguments.env_file)
    settings.require_runtime_storage()
    assert settings.database_url is not None
    now = datetime.now(TORONTO)
    if now.hour < 16:
        parser.error("The daily update is available after the regular market closes at 4:00 p.m. Toronto time.")
    score_date = now.date()
    if not _symbols(settings.database_url, score_date):
        parser.error("No current S&P 500 universe is available for today.")

    environment = dict(os.environ)
    environment.update(_dotenv_values(arguments.env_file))
    environment["PYTHONPATH"] = str(Path("services/research/src").resolve())
    revision = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True).strip()
    symbol_list = _symbols(settings.database_url, score_date)
    symbols = ",".join(symbol_list)
    ciks = ",".join(_ciks(settings.database_url, score_date))

    with _daily_update_lock(settings.database_url) as connection:
        should_run, retry_cutoff = _start_or_resume(connection, score_date)
        if not should_run:
            print(f"already_completed score_date={score_date}; no duplicate publication was created")
            return
        try:
            existing_score = _published_score_summary(settings.database_url, score_date, len(symbol_list))
            if existing_score is not None:
                decision_at, snapshots, eligible = existing_score
                _set_decision_at(connection, score_date, decision_at)
                score_note = f"score_snapshots={snapshots}; eligible={eligible}"
                print(f"reusing_existing_scores score_date={score_date}; snapshots={snapshots}; eligible={eligible}")
            else:
                start = _catch_up_start(settings.database_url, score_date)
                if start <= score_date:
                    _run([sys.executable, "-m", "quantrade_research.ingest_market_data", "--symbols", symbols,
                          "--start", start.isoformat(), "--end", score_date.isoformat(), "--code-revision", revision], environment)
                    _run([sys.executable, "-m", "quantrade_research.ingest_benchmark_data", "--ticker", "SPY",
                          "--start", start.isoformat(), "--end", score_date.isoformat(), "--code-revision", revision], environment)
                if not _has_current_benchmark_session(settings.database_url, score_date):
                    _set_skipped(connection, score_date, "No regular SPY session was returned for this date.")
                    print(f"skipped score_date={score_date}; no regular NYSE session")
                    return
                if ciks:
                    _run([sys.executable, "-m", "quantrade_research.ingest_filings", "--ciks", ciks,
                          "--code-revision", revision, "--incremental"], environment)
                decision_at = _set_decision_at(connection, score_date, retry_cutoff)
                score_note = _run([sys.executable, "-m", "quantrade_research.score_run", "--score-date", score_date.isoformat(),
                                   "--code-revision", revision, "--manual", "--decision-at", decision_at.isoformat()], environment)
                snapshot_text, eligible_text = score_note.split("; ")
                snapshots, eligible = int(snapshot_text.split("=")[1]), int(eligible_text.split("=")[1])
            _set_completed(connection, score_date, snapshots, eligible)
        except Exception as error:
            _set_failure(connection, score_date, str(error))
            raise

    try:
        forward_outcomes = materialize_due_forward_score_outcomes(settings=settings, as_of_date=score_date)
        outcomes = materialize_due_paper_portfolio_outcomes(settings=settings, as_of_date=score_date)
        published_portfolios = publish_due_paper_portfolios(settings=settings, execution_date=score_date)
    except Exception as error:
        print(f"completed score_date={score_date}; {score_note}; post_publication_error={error}")
        return

    published_note = ",".join(item.isoformat() for item in published_portfolios) or "none_due"
    outcome_note = ",".join(f"{item.horizon_sessions}d:{item.status}" for item in outcomes) or "none_due"
    forward_note = ",".join(f"{item.horizon_sessions}d:{item.status}" for item in forward_outcomes) or "none_due"
    print(f"completed score_date={score_date}; {score_note}; forward_outcomes={forward_note}; paper_portfolios={published_note}; paper_outcomes={outcome_note}")


if __name__ == "__main__":
    main()
