"""Private post-close refresh: market bars, benchmark, then a manual score run."""

from __future__ import annotations

import argparse
from datetime import datetime
import os
from pathlib import Path
import subprocess
import sys

from .score_run import TORONTO, _dotenv_values, _settings


def _symbols(database_url: str, score_date) -> list[str]:
    import psycopg
    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute("""SELECT l.ticker FROM quantrade.universe_snapshots u
                          JOIN quantrade.universe_memberships m ON m.universe_snapshot_id = u.universe_snapshot_id
                          JOIN quantrade.listings l ON l.security_id = m.security_id
                          WHERE u.universe_code = 'sp500' AND u.as_of_date <= %s AND l.valid_to IS NULL
                          ORDER BY u.as_of_date DESC, l.ticker""", (score_date,))
        return sorted(set(str(row[0]) for row in cursor.fetchall()))


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the private manual daily Quantrade update")
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    arguments = parser.parse_args()
    settings = _settings(arguments.env_file)
    settings.require_runtime_storage()
    assert settings.database_url is not None
    now = datetime.now(TORONTO)
    if now.hour < 16:
        parser.error("The manual update is available after the regular market closes at 4:00 p.m. Toronto time.")
    score_date = now.date()
    if not _symbols(settings.database_url, score_date):
        parser.error("No current S&P 500 universe is available for today.")
    environment = dict(os.environ)
    environment.update(_dotenv_values(arguments.env_file))
    environment["PYTHONPATH"] = str(Path("services/research/src").resolve())
    revision = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True).strip()
    symbols = ",".join(_symbols(settings.database_url, score_date))
    commands = (
        [sys.executable, "-m", "quantrade_research.ingest_market_data", "--symbols", symbols, "--start", score_date.isoformat(), "--end", score_date.isoformat(), "--code-revision", revision],
        [sys.executable, "-m", "quantrade_research.ingest_benchmark_data", "--ticker", "SPY", "--start", score_date.isoformat(), "--end", score_date.isoformat(), "--code-revision", revision],
        [sys.executable, "-m", "quantrade_research.score_run", "--score-date", score_date.isoformat(), "--code-revision", revision, "--manual"],
    )
    for command in commands:
        subprocess.run(command, env=environment, check=True)
    print(f"completed score_date={score_date}")


if __name__ == "__main__":
    main()
