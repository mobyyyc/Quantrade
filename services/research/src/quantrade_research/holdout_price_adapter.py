"""Build execution-period input from PostgreSQL without changing frozen selections."""

from __future__ import annotations

import argparse
from datetime import date
from decimal import Decimal
import json
import os
from pathlib import Path
from typing import Protocol

from .corporate_action_coverage import require_corporate_action_coverage
from .execution_cost_evaluation import load_selection_manifest
from .holdout_evaluation import require_locked_holdout_confirmation
from .quality import DataQualityError
from .score_run import _dotenv_values


class HoldoutPriceSource(Protocol):
    def require_corporate_action_coverage(self, start_date: date, end_date: date) -> None: ...
    def next_benchmark_session(self, formation_date: date) -> date | None: ...
    def security_opens(self, security_ids: tuple[str, ...], session_date: date) -> dict[str, Decimal]: ...
    def benchmark_open(self, session_date: date) -> Decimal | None: ...
    def corporate_action_security_ids(self, security_ids: tuple[str, ...], start_date: date, end_date: date) -> frozenset[str]: ...


def _security_ids(formation: dict[str, object], strategy: str) -> tuple[str, ...]:
    try:
        return tuple(str(row["security_id"]) for row in formation[strategy])  # type: ignore[index]
    except (KeyError, TypeError) as error:
        raise DataQualityError(f"selection manifest is missing {strategy} positions") from error


def _formation_date(formation: dict[str, object]) -> date:
    try:
        return date.fromisoformat(str(formation["formation_date"]))
    except (KeyError, TypeError, ValueError) as error:
        raise DataQualityError("selection manifest has an invalid formation date") from error


def build_execution_period_input(manifest: dict[str, object], source: HoldoutPriceSource) -> dict[str, object]:
    """Use the first SPY session after each formation; never shift a missing equity open."""
    formations = list(manifest["formations"])  # type: ignore[index]
    if not formations:
        raise DataQualityError("selection manifest has no frozen formations")
    formation_dates = [_formation_date(formation) for formation in formations if isinstance(formation, dict)]
    if len(formation_dates) != len(formations):
        raise DataQualityError("selection manifest contains an invalid formation")
    source.require_corporate_action_coverage(min(formation_dates), max(formation_dates))
    prepared: list[tuple[date, dict[str, object], date, tuple[str, ...]] | None] = []
    withheld: list[dict[str, str]] = []
    for formation in formations:
        if not isinstance(formation, dict):
            raise DataQualityError("selection manifest contains an invalid formation")
        formation_date = _formation_date(formation)
        union = tuple(sorted(set(_security_ids(formation, "baseline")) | set(_security_ids(formation, "elastic_net"))))
        execution_date = source.next_benchmark_session(formation_date)
        if execution_date is None:
            withheld.append({"formation_date": formation_date.isoformat(), "reason": "no next SPY regular-session open"})
            prepared.append(None)
            continue
        if execution_date <= formation_date:
            raise DataQualityError("price source returned a non-forward execution date")
        equity_opens = source.security_opens(union, execution_date)
        benchmark_open = source.benchmark_open(execution_date)
        missing = sorted(set(union) - equity_opens.keys())
        if missing or benchmark_open is None or benchmark_open <= 0:
            reason = "missing next-open marks for shared frozen universe"
            if missing:
                reason += ": " + ", ".join(missing)
            withheld.append({"formation_date": formation_date.isoformat(), "reason": reason})
            prepared.append(None)
            continue
        if any(value <= 0 for value in equity_opens.values()):
            raise DataQualityError(f"price source returned a non-positive equity open for {formation_date}")
        prepared.append((formation_date, formation, execution_date, union))

    periods: list[dict[str, object]] = []
    for index in range(len(prepared) - 1):
        current = prepared[index]
        following = prepared[index + 1]
        if current is None:
            continue
        formation_date, formation, execution_date, union = current
        if following is None:
            withheld.append({
                "formation_date": formation_date.isoformat(),
                "reason": "following frozen rebalance execution is unavailable; fixed open-to-open period withheld",
            })
            continue
        exit_date = following[2]
        exit_opens = source.security_opens(union, exit_date)
        benchmark_entry = source.benchmark_open(execution_date)
        benchmark_exit = source.benchmark_open(exit_date)
        missing = sorted(set(union) - exit_opens.keys())
        if missing or benchmark_entry is None or benchmark_exit is None or benchmark_entry <= 0 or benchmark_exit <= 0:
            reason = "missing next-open marks for fixed exit date"
            if missing:
                reason += ": " + ", ".join(missing)
            withheld.append({"formation_date": formation_date.isoformat(), "reason": reason})
            continue
        actions = source.corporate_action_security_ids(union, execution_date, exit_date)
        periods.append({
            "formation_date": formation_date.isoformat(),
            "execution_date": execution_date.isoformat(),
            "exit_date": exit_date.isoformat(),
            "entry_prices": {security_id: str(value) for security_id, value in source.security_opens(union, execution_date).items()},
            "exit_prices": {security_id: str(value) for security_id, value in exit_opens.items()},
            "benchmark_entry_price": str(benchmark_entry),
            "benchmark_exit_price": str(benchmark_exit),
            "corporate_action_security_ids": sorted(actions),
            "corporate_action_position_accounting": getattr(source, "corporate_action_position_accounting", "not_verified"),
        })
    if prepared and prepared[-1] is not None:
        withheld.append({"formation_date": prepared[-1][0].isoformat(), "reason": "no following frozen rebalance execution date for an open-to-open exit"})
    return {
        "status": "execution_period_input_prepared",
        "price_basis": getattr(source, "price_basis", "unadjusted regular-session opens"),
        "benchmark_ticker": "SPY",
        "periods": periods,
        "withheld_formations": withheld,
        "next_step": "Use the frozen-selection evaluator exactly once after explicit approval; withheld formations remain excluded.",
    }


class PostgresHoldoutPriceSource:
    """Read-only PostgreSQL source for the pre-registered next-open convention."""

    def __init__(self, database_url: str, *, adjustment_basis: str = "unadjusted") -> None:
        import psycopg

        self._database_url = database_url
        self._connection = psycopg.connect(database_url)
        if adjustment_basis not in {"unadjusted", "total_return_adjusted"}:
            raise DataQualityError("holdout source requires unadjusted or total-return-adjusted prices")
        self._adjustment_basis = adjustment_basis
        self.price_basis = f"{adjustment_basis} regular-session opens"
        self.corporate_action_position_accounting = (
            "provider_total_return_adjusted_prices"
            if adjustment_basis == "total_return_adjusted" else "not_verified"
        )

    def close(self) -> None:
        self._connection.close()

    def require_corporate_action_coverage(self, start_date: date, end_date: date) -> None:
        """Fail closed unless a completed, raw-backed cohort backfill covers the window."""
        require_corporate_action_coverage(
            self._database_url,
            start_date=start_date,
            end_date=end_date,
        )

    def next_benchmark_session(self, formation_date: date) -> date | None:
        with self._connection.cursor() as cursor:
            cursor.execute(
                """SELECT session_date FROM quantrade.benchmark_daily_price_bars
                   WHERE benchmark_ticker = 'SPY' AND session = 'regular'
                     AND adjustment_basis = %s AND session_date > %s
                   ORDER BY session_date ASC LIMIT 1""",
                (self._adjustment_basis, formation_date),
            )
            row = cursor.fetchone()
        return row[0] if row else None

    def security_opens(self, security_ids: tuple[str, ...], session_date: date) -> dict[str, Decimal]:
        with self._connection.cursor() as cursor:
            cursor.execute(
                """SELECT security_id::text, open_price FROM quantrade.daily_price_bars
                   WHERE security_id = ANY(%s::uuid[]) AND session_date = %s
                     AND session = 'regular' AND adjustment_basis = %s""",
                (list(security_ids), session_date, self._adjustment_basis),
            )
            return {str(row[0]): row[1] for row in cursor.fetchall()}

    def benchmark_open(self, session_date: date) -> Decimal | None:
        with self._connection.cursor() as cursor:
            cursor.execute(
                """SELECT open_price FROM quantrade.benchmark_daily_price_bars
                   WHERE benchmark_ticker = 'SPY' AND session_date = %s
                     AND session = 'regular' AND adjustment_basis = %s""",
                (session_date, self._adjustment_basis),
            )
            row = cursor.fetchone()
        return row[0] if row else None

    def corporate_action_security_ids(self, security_ids: tuple[str, ...], start_date: date, end_date: date) -> frozenset[str]:
        with self._connection.cursor() as cursor:
            cursor.execute(
                """SELECT DISTINCT security_id::text FROM quantrade.corporate_actions
                   WHERE security_id = ANY(%s::uuid[])
                     AND COALESCE(effective_date, process_date) >= %s
                     AND COALESCE(effective_date, process_date) <= %s""",
                (list(security_ids), start_date, end_date),
            )
            return frozenset(str(row[0]) for row in cursor.fetchall())


def _settings(env_file: Path):
    from .config import Settings

    values = dict(os.environ)
    values.update(_dotenv_values(env_file))
    return Settings.from_environment(values)


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare frozen holdout next-open execution periods from PostgreSQL")
    parser.add_argument("--selection-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--adjustment-basis", choices=("unadjusted", "total_return_adjusted"), default="unadjusted")
    parser.add_argument("--confirm-locked-holdout", action="store_true")
    arguments = parser.parse_args()
    require_locked_holdout_confirmation(arguments.confirm_locked_holdout)
    if arguments.output.exists():
        raise DataQualityError(f"refusing to overwrite immutable execution-period input: {arguments.output}")
    settings = _settings(arguments.env_file)
    settings.require_runtime_storage()
    assert settings.database_url is not None
    source = PostgresHoldoutPriceSource(settings.database_url, adjustment_basis=arguments.adjustment_basis)
    try:
        document = build_execution_period_input(load_selection_manifest(arguments.selection_manifest), source)
    finally:
        source.close()
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"execution_periods={len(document['periods'])}; withheld_formations={len(document['withheld_formations'])}")


if __name__ == "__main__":
    main()
