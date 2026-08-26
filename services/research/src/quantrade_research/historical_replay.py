"""Replay fixed-cohort historical decisions without using later observations."""

from __future__ import annotations

import argparse
from datetime import date, datetime, time
from pathlib import Path
import subprocess

from .score_run import TORONTO, _settings, run_score_generation


DEFAULT_COHORT = "sp500_current_survivors_v1"
DEFAULT_START = date(2021, 1, 1)
DEFAULT_END = date(2026, 6, 30)


def historical_decision_at(session_date: date) -> datetime:
    """The fixed 8 p.m. Toronto decision timestamp for one historical session."""
    return datetime.combine(session_date, time(20, 0), tzinfo=TORONTO)


def replayable_session_dates(
    session_dates: list[date], *, start_date: date, end_date: date,
) -> tuple[date, ...]:
    """Keep the supplied regular sessions in deterministic date order."""
    if end_date < start_date:
        raise ValueError("historical replay end date must not be before its start date")
    return tuple(sorted({session_date for session_date in session_dates if start_date <= session_date <= end_date}))


def _session_dates(database_url: str, start_date: date, end_date: date) -> tuple[date, ...]:
    import psycopg

    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute(
            """SELECT session_date
               FROM quantrade.benchmark_daily_price_bars
               WHERE benchmark_ticker = 'SPY' AND session = 'regular'
                 AND adjustment_basis = 'split_adjusted'
                 AND session_date BETWEEN %s AND %s
                 AND available_at <= ((session_date::timestamp + TIME '20:00') AT TIME ZONE 'America/Toronto')
               ORDER BY session_date""",
            (start_date, end_date),
        )
        candidates = [row[0] for row in cursor.fetchall()]
    # The availability predicate is deliberately in SQL so a full replay does
    # not issue a separate database round trip for every historical session.
    return replayable_session_dates(candidates, start_date=start_date, end_date=end_date)


def _is_completed(database_url: str, score_date: date) -> bool:
    import psycopg

    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT status = 'completed' FROM quantrade.daily_research_runs WHERE score_date = %s",
            (score_date,),
        )
        row = cursor.fetchone()
        return bool(row and row[0])


def _start_run(database_url: str, score_date: date) -> None:
    import psycopg

    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute(
            """INSERT INTO quantrade.daily_research_runs (score_date, status, started_at)
               VALUES (%s, 'running', now())
               ON CONFLICT (score_date) DO UPDATE
               SET status = 'running', started_at = EXCLUDED.started_at, completed_at = NULL,
                   score_snapshot_count = NULL, eligible_count = NULL, failure_reason = NULL""",
            (score_date,),
        )
        connection.commit()


def _complete_run(database_url: str, score_date: date, decision_at: datetime, snapshots: int, eligible: int) -> None:
    import psycopg

    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute(
            """UPDATE quantrade.daily_research_runs
               SET status = 'completed', decision_at = %s, completed_at = now(),
                   score_snapshot_count = %s, eligible_count = %s, failure_reason = NULL
               WHERE score_date = %s""",
            (decision_at, snapshots, eligible, score_date),
        )
        connection.commit()


def _fail_run(database_url: str, score_date: date, error: Exception) -> None:
    import psycopg

    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute(
            """UPDATE quantrade.daily_research_runs
               SET status = 'failed', completed_at = now(), failure_reason = %s
               WHERE score_date = %s""",
            (str(error), score_date),
        )
        connection.commit()


def replay_historical_sessions(*, settings, start_date: date, end_date: date, cohort_code: str,
                               code_revision: str, limit: int | None = None) -> tuple[int, int, int]:
    """Resume-safe replay; incomplete feature inputs become immutable unavailable snapshots."""
    settings.require_runtime_storage()
    assert settings.database_url is not None
    sessions = _session_dates(settings.database_url, start_date, end_date)
    if limit is not None:
        sessions = sessions[:limit]
    replayed = skipped = eligible_total = 0
    for score_date in sessions:
        if _is_completed(settings.database_url, score_date):
            skipped += 1
            continue
        decision_at = historical_decision_at(score_date)
        _start_run(settings.database_url, score_date)
        try:
            snapshots, eligible = run_score_generation(
                settings=settings, score_date=score_date, universe_code="sp500", benchmark_ticker="SPY",
                code_revision=code_revision, decision_at=decision_at, research_cohort_code=cohort_code,
            )
            _complete_run(settings.database_url, score_date, decision_at, snapshots, eligible)
        except Exception as error:
            _fail_run(settings.database_url, score_date, error)
            raise
        replayed += 1
        eligible_total += eligible
    return replayed, skipped, eligible_total


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay Tier-B historical baseline decisions at 8 p.m. Toronto time")
    parser.add_argument("--start", type=date.fromisoformat, default=DEFAULT_START)
    parser.add_argument("--end", type=date.fromisoformat, default=DEFAULT_END)
    parser.add_argument("--cohort", default=DEFAULT_COHORT)
    parser.add_argument("--limit", type=int, help="Process only the first N eligible sessions; useful for controlled batches")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    arguments = parser.parse_args()
    if arguments.limit is not None and arguments.limit <= 0:
        parser.error("--limit must be positive")
    settings = _settings(arguments.env_file)
    settings.require_runtime_storage()
    assert settings.database_url is not None
    sessions = _session_dates(settings.database_url, arguments.start, arguments.end)
    if arguments.limit is not None:
        sessions = sessions[:arguments.limit]
    if arguments.dry_run:
        print(f"replayable_sessions={len(sessions)}; cohort={arguments.cohort}; start={arguments.start}; end={arguments.end}")
        return
    revision = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True).strip()
    replayed, skipped, eligible = replay_historical_sessions(
        settings=settings, start_date=arguments.start, end_date=arguments.end, cohort_code=arguments.cohort,
        code_revision=revision, limit=arguments.limit,
    )
    print(f"replayed_sessions={replayed}; skipped_completed={skipped}; eligible_snapshots={eligible}; cohort={arguments.cohort}")


if __name__ == "__main__":
    main()
