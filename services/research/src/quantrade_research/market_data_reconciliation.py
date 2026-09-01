"""Read-only Alpaca reconciliation against the normalized market-data ledger."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import json
from pathlib import Path
from typing import Callable, Iterable

from .alpaca import AlpacaClient, AlpacaCorporateAction, AlpacaDailyBar, parse_corporate_actions, parse_daily_bars
from .historical_cohorts import CURRENT_SURVIVORS_COHORT
from .quality import DataQualityError
from .score_run import _settings
from .universe_symbols import canonical_ticker


REPORT_SCHEMA_VERSION = "alpaca_market_reconciliation_v1"
BAR_ADJUSTMENTS = (("raw", "unadjusted"), ("split", "split_adjusted"))
RECONCILED_ACTION_TYPES = frozenset({
    "forward_split", "reverse_split", "unit_split", "cash_dividend", "stock_dividend",
})
PRICE_TOLERANCE = Decimal("0.00000001")


@dataclass(frozen=True, slots=True)
class BarRecord:
    ticker: str
    session_date: date
    adjustment_basis: str
    open_price: Decimal
    high_price: Decimal
    low_price: Decimal
    close_price: Decimal
    volume: Decimal

    @property
    def key(self) -> tuple[str, date, str]:
        return self.ticker, self.session_date, self.adjustment_basis


@dataclass(frozen=True, slots=True)
class ActionRecord:
    provider_action_id: str
    ticker: str
    action_type: str
    process_date: date
    effective_date: date | None
    cash_amount: Decimal | None
    ratio_numerator: Decimal | None
    ratio_denominator: Decimal | None


def _bar_record(bar: AlpacaDailyBar, adjustment_basis: str) -> BarRecord:
    return BarRecord(
        ticker=bar.ticker, session_date=bar.session_date, adjustment_basis=adjustment_basis,
        open_price=bar.open_price, high_price=bar.high_price, low_price=bar.low_price,
        close_price=bar.close_price, volume=bar.volume,
    )


def _action_record(action: AlpacaCorporateAction) -> ActionRecord:
    return ActionRecord(
        provider_action_id=action.provider_action_id, ticker=action.ticker,
        action_type=action.action_type, process_date=action.process_date,
        effective_date=action.effective_date, cash_amount=action.cash_amount,
        ratio_numerator=action.ratio_numerator, ratio_denominator=action.ratio_denominator,
    )


def _bar_difference(provider: BarRecord, ledger: BarRecord) -> tuple[str, ...]:
    changed: list[str] = []
    for field in ("open_price", "high_price", "low_price", "close_price"):
        if abs(getattr(provider, field) - getattr(ledger, field)) > PRICE_TOLERANCE:
            changed.append(field)
    if provider.volume != ledger.volume:
        changed.append("volume")
    return tuple(changed)


def _serialize_bar_key(key: tuple[str, date, str]) -> dict[str, str]:
    return {"ticker": key[0], "session_date": key[1].isoformat(), "adjustment_basis": key[2]}


def compare_bars(
    provider_bars: Iterable[BarRecord], ledger_bars: Iterable[BarRecord], *,
    symbols: Iterable[str], expected_sessions: Iterable[date], sample_limit: int = 25,
) -> dict[str, object]:
    provider = {bar.key: bar for bar in provider_bars}
    ledger = {bar.key: bar for bar in ledger_bars}
    missing_in_ledger = sorted(set(provider) - set(ledger))
    missing_at_provider = sorted(set(ledger) - set(provider))
    mismatches = []
    for key in sorted(set(provider) & set(ledger)):
        changed = _bar_difference(provider[key], ledger[key])
        if changed:
            mismatches.append({**_serialize_bar_key(key), "changed_fields": list(changed)})

    expected = set(expected_sessions)
    provider_split_sessions: dict[str, set[date]] = {}
    ledger_split_sessions: dict[str, set[date]] = {}
    for bar in provider.values():
        if bar.adjustment_basis == "split_adjusted":
            provider_split_sessions.setdefault(bar.ticker, set()).add(bar.session_date)
    for bar in ledger.values():
        if bar.adjustment_basis == "split_adjusted":
            ledger_split_sessions.setdefault(bar.ticker, set()).add(bar.session_date)
    provider_session_gaps: list[dict[str, str]] = []
    ledger_session_gaps: list[dict[str, str]] = []
    for symbol in sorted(set(symbols)):
        provider_session_gaps.extend(
            {"ticker": symbol, "session_date": session.isoformat()}
            for session in sorted(expected - provider_split_sessions.get(symbol, set()))
        )
        ledger_session_gaps.extend(
            {"ticker": symbol, "session_date": session.isoformat()}
            for session in sorted(expected - ledger_split_sessions.get(symbol, set()))
        )

    return {
        "provider_row_count": len(provider),
        "ledger_row_count": len(ledger),
        "matched_row_count": len(set(provider) & set(ledger)) - len(mismatches),
        "missing_in_ledger_count": len(missing_in_ledger),
        "missing_at_provider_count": len(missing_at_provider),
        "value_mismatch_count": len(mismatches),
        "provider_session_gap_count": len(provider_session_gaps),
        "ledger_session_gap_count": len(ledger_session_gaps),
        "samples": {
            "missing_in_ledger": [_serialize_bar_key(key) for key in missing_in_ledger[:sample_limit]],
            "missing_at_provider": [_serialize_bar_key(key) for key in missing_at_provider[:sample_limit]],
            "value_mismatches": mismatches[:sample_limit],
            "provider_session_gaps": provider_session_gaps[:sample_limit],
            "ledger_session_gaps": ledger_session_gaps[:sample_limit],
        },
    }


def _action_fields(record: ActionRecord) -> tuple[object, ...]:
    return (
        record.action_type, record.process_date, record.effective_date,
        record.cash_amount, record.ratio_numerator, record.ratio_denominator,
    )


def compare_actions(
    provider_actions: Iterable[ActionRecord], ledger_actions: Iterable[ActionRecord], *, sample_limit: int = 25,
) -> dict[str, object]:
    provider = {action.provider_action_id: action for action in provider_actions if action.action_type in RECONCILED_ACTION_TYPES}
    ledger = {action.provider_action_id: action for action in ledger_actions if action.action_type in RECONCILED_ACTION_TYPES}
    missing_in_ledger = sorted(set(provider) - set(ledger))
    missing_at_provider = sorted(set(ledger) - set(provider))
    mismatches = []
    for identifier in sorted(set(provider) & set(ledger)):
        if _action_fields(provider[identifier]) != _action_fields(ledger[identifier]):
            mismatches.append({
                "provider_action_id": identifier,
                "provider": _serialize_action(provider[identifier]),
                "ledger": _serialize_action(ledger[identifier]),
            })
    return {
        "provider_action_count": len(provider),
        "ledger_action_count": len(ledger),
        "matched_action_count": len(set(provider) & set(ledger)) - len(mismatches),
        "missing_in_ledger_count": len(missing_in_ledger),
        "missing_at_provider_count": len(missing_at_provider),
        "value_mismatch_count": len(mismatches),
        "samples": {
            "missing_in_ledger": [_serialize_action(provider[key]) for key in missing_in_ledger[:sample_limit]],
            "missing_at_provider": [_serialize_action(ledger[key]) for key in missing_at_provider[:sample_limit]],
            "value_mismatches": mismatches[:sample_limit],
        },
    }


def _serialize_action(action: ActionRecord) -> dict[str, str | None]:
    return {
        "provider_action_id": action.provider_action_id,
        "ticker": action.ticker,
        "action_type": action.action_type,
        "process_date": action.process_date.isoformat(),
        "effective_date": action.effective_date.isoformat() if action.effective_date else None,
        "cash_amount": str(action.cash_amount) if action.cash_amount is not None else None,
        "ratio_numerator": str(action.ratio_numerator) if action.ratio_numerator is not None else None,
        "ratio_denominator": str(action.ratio_denominator) if action.ratio_denominator is not None else None,
    }


class PostgresReconciliationRepository:
    def __init__(self, database_url: str) -> None:
        import psycopg
        self._connection = psycopg.connect(database_url)
        self._security_id_by_symbol: dict[str, str] = {}

    def close(self) -> None:
        self._connection.close()

    def latest_benchmark_session(self, ticker: str = "SPY") -> date:
        with self._connection.cursor() as cursor:
            cursor.execute(
                """SELECT MAX(session_date) FROM quantrade.benchmark_daily_price_bars
                   WHERE benchmark_ticker = %s AND session = 'regular' AND adjustment_basis = 'split_adjusted'""",
                (ticker,),
            )
            row = cursor.fetchone()
        if not row or row[0] is None:
            raise DataQualityError(f"no split-adjusted {ticker} benchmark session is available")
        return row[0]

    def cohort_symbols(self, cohort_code: str) -> list[str]:
        with self._connection.cursor() as cursor:
            cursor.execute(
                """SELECT membership.security_id::text, array_agg(DISTINCT listing.ticker ORDER BY listing.ticker)
                   FROM quantrade.research_cohort_memberships membership
                   JOIN quantrade.research_cohorts cohort ON cohort.research_cohort_id = membership.research_cohort_id
                   JOIN quantrade.listings listing ON listing.security_id = membership.security_id AND listing.valid_to IS NULL
                   WHERE cohort.cohort_code = %s
                   GROUP BY membership.security_id""",
                (cohort_code,),
            )
            pairs = [(str(row[0]), canonical_ticker(str(value) for value in row[1])) for row in cursor.fetchall()]
        self._security_id_by_symbol = {symbol: security_id for security_id, symbol in pairs}
        return sorted(self._security_id_by_symbol)

    def _security_ids(self, symbols: list[str]) -> list[str]:
        try:
            return [self._security_id_by_symbol[symbol] for symbol in symbols]
        except KeyError as error:
            raise DataQualityError("cohort symbols must be loaded before ledger reconciliation") from error

    def stock_bars(self, symbols: list[str], start: date, end: date) -> list[BarRecord]:
        with self._connection.cursor() as cursor:
            cursor.execute(
                """SELECT bar.security_id::text, bar.session_date, bar.adjustment_basis,
                          bar.open_price, bar.high_price, bar.low_price, bar.close_price, bar.volume
                   FROM quantrade.daily_price_bars bar
                   WHERE bar.security_id = ANY(%s::uuid[]) AND bar.session = 'regular'
                     AND bar.adjustment_basis = ANY(%s) AND bar.session_date BETWEEN %s AND %s""",
                (self._security_ids(symbols), [basis for _, basis in BAR_ADJUSTMENTS], start, end),
            )
            symbol_by_security_id = {security_id: symbol for symbol, security_id in self._security_id_by_symbol.items()}
            return [BarRecord(symbol_by_security_id[str(row[0])], row[1], str(row[2]), *(Decimal(str(value)) for value in row[3:])) for row in cursor.fetchall()]

    def benchmark_bars(self, ticker: str, start: date, end: date) -> list[BarRecord]:
        with self._connection.cursor() as cursor:
            cursor.execute(
                """SELECT benchmark_ticker, session_date, adjustment_basis,
                          open_price, high_price, low_price, close_price, volume
                   FROM quantrade.benchmark_daily_price_bars
                   WHERE benchmark_ticker = %s AND session = 'regular'
                     AND adjustment_basis = ANY(%s) AND session_date BETWEEN %s AND %s""",
                (ticker, [basis for _, basis in BAR_ADJUSTMENTS], start, end),
            )
            return [BarRecord(str(row[0]), row[1], str(row[2]), *(Decimal(str(value)) for value in row[3:])) for row in cursor.fetchall()]

    def stock_actions(self, symbols: list[str], start: date, end: date) -> list[ActionRecord]:
        with self._connection.cursor() as cursor:
            cursor.execute(
                """SELECT action.provider_action_id, action.security_id::text, action.action_type,
                          action.process_date, action.effective_date, action.cash_amount,
                          action.ratio_numerator, action.ratio_denominator
                   FROM quantrade.corporate_actions action
                   WHERE action.security_id = ANY(%s::uuid[]) AND action.process_date BETWEEN %s AND %s
                     AND action.action_type = ANY(%s)""",
                (self._security_ids(symbols), start, end, list(RECONCILED_ACTION_TYPES)),
            )
            symbol_by_security_id = {security_id: symbol for symbol, security_id in self._security_id_by_symbol.items()}
            return [_action_from_row((row[0], symbol_by_security_id[str(row[1])], *row[2:])) for row in cursor.fetchall()]

    def benchmark_actions(self, ticker: str, start: date, end: date) -> list[ActionRecord]:
        with self._connection.cursor() as cursor:
            cursor.execute(
                """SELECT provider_action_id, benchmark_ticker, action_type, process_date,
                          effective_date, cash_amount, ratio_numerator, ratio_denominator
                   FROM quantrade.benchmark_corporate_actions
                   WHERE benchmark_ticker = %s AND process_date BETWEEN %s AND %s
                     AND action_type = ANY(%s)""",
                (ticker, start, end, list(RECONCILED_ACTION_TYPES)),
            )
            return [_action_from_row(row) for row in cursor.fetchall()]


def _action_from_row(row) -> ActionRecord:
    return ActionRecord(
        str(row[0]), str(row[1]), str(row[2]), row[3], row[4],
        Decimal(str(row[5])) if row[5] is not None else None,
        Decimal(str(row[6])) if row[6] is not None else None,
        Decimal(str(row[7])) if row[7] is not None else None,
    )


def _fetch_bar_records(client: AlpacaClient, symbols: list[str], start: date, end: date) -> list[BarRecord]:
    records: list[BarRecord] = []
    for adjustment, basis in BAR_ADJUSTMENTS:
        token = None
        while True:
            bars, token = parse_daily_bars(client.fetch_daily_bars(symbols, start, end, adjustment, token))
            records.extend(_bar_record(bar, basis) for bar in bars)
            if token is None:
                break
    return records


def _fetch_action_records(client: AlpacaClient, symbols: list[str], start: date, end: date) -> list[ActionRecord]:
    records: list[ActionRecord] = []
    token = None
    while True:
        actions, token = parse_corporate_actions(client.fetch_corporate_actions(symbols, start, end, token))
        records.extend(_action_record(action) for action in actions if action.action_type in RECONCILED_ACTION_TYPES)
        if token is None:
            break
    return records


def _finding_count(section: dict[str, object], keys: tuple[str, ...]) -> int:
    return sum(int(section[key]) for key in keys)


def run_reconciliation(
    *, repository: PostgresReconciliationRepository, client: AlpacaClient, cohort_code: str,
    benchmark_ticker: str, start: date, end: date, batch_size: int, sample_limit: int,
    code_revision: str, progress: Callable[[str], None] | None = None,
) -> dict[str, object]:
    symbols = repository.cohort_symbols(cohort_code)
    if not symbols:
        raise DataQualityError(f"cohort {cohort_code} has no active listings")
    provider_stock_bars: list[BarRecord] = []
    provider_stock_actions: list[ActionRecord] = []
    batches = [symbols[index:index + batch_size] for index in range(0, len(symbols), batch_size)]
    for index, batch in enumerate(batches, start=1):
        provider_stock_bars.extend(_fetch_bar_records(client, batch, start, end))
        provider_stock_actions.extend(_fetch_action_records(client, batch, start, end))
        if progress:
            progress(f"reconciled provider batch {index}/{len(batches)} ({len(batch)} symbols)")

    provider_benchmark_bars = _fetch_bar_records(client, [benchmark_ticker], start, end)
    provider_benchmark_actions = _fetch_action_records(client, [benchmark_ticker], start, end)
    expected_sessions = sorted({
        bar.session_date for bar in provider_benchmark_bars if bar.adjustment_basis == "split_adjusted"
    })
    if not expected_sessions:
        raise DataQualityError(f"Alpaca returned no {benchmark_ticker} sessions for {start} through {end}")

    stock_bars = compare_bars(
        provider_stock_bars, repository.stock_bars(symbols, start, end), symbols=symbols,
        expected_sessions=expected_sessions, sample_limit=sample_limit,
    )
    benchmark_bars = compare_bars(
        provider_benchmark_bars, repository.benchmark_bars(benchmark_ticker, start, end),
        symbols=[benchmark_ticker], expected_sessions=expected_sessions, sample_limit=sample_limit,
    )
    stock_actions = compare_actions(
        provider_stock_actions, repository.stock_actions(symbols, start, end), sample_limit=sample_limit,
    )
    benchmark_actions = compare_actions(
        provider_benchmark_actions, repository.benchmark_actions(benchmark_ticker, start, end), sample_limit=sample_limit,
    )
    actionable_keys = ("missing_in_ledger_count", "value_mismatch_count")
    coverage_keys = ("missing_at_provider_count", "provider_session_gap_count")
    actionable = sum(_finding_count(section, actionable_keys) for section in (stock_bars, benchmark_bars, stock_actions, benchmark_actions))
    coverage = sum(_finding_count(section, coverage_keys) for section in (stock_bars, benchmark_bars))
    coverage += sum(int(section["missing_at_provider_count"]) for section in (stock_actions, benchmark_actions))
    return {
        "report_schema_version": REPORT_SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "code_revision": code_revision,
        "provider": "alpaca",
        "cohort_code": cohort_code,
        "data_capability_tier": "B",
        "window": {"start": start.isoformat(), "end": end.isoformat()},
        "benchmark_ticker": benchmark_ticker,
        "cohort_symbol_count": len(symbols),
        "expected_market_session_count": len(expected_sessions),
        "ledger_consistent": actionable == 0,
        "provider_coverage_complete": coverage == 0,
        "status": "clean" if actionable == 0 and coverage == 0 else "findings",
        "actionable_finding_count": actionable,
        "provider_coverage_finding_count": coverage,
        "stock_bars": stock_bars,
        "benchmark_bars": benchmark_bars,
        "stock_splits_and_dividends": stock_actions,
        "benchmark_splits_and_dividends": benchmark_actions,
        "limitations": [
            "Read-only reconciliation never repairs or rewrites normalized market data.",
            "Alpaca Basic IEX coverage is Tier B and is not an independent licensed reference source.",
            "Provider omissions are reported separately from ledger omissions.",
            "Raw and split-adjusted bars are the periodic price scope; provider total-return bars remain a separate research audit.",
            "Only splits, cash dividends, and stock dividends are included in this periodic action check.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Reconcile Alpaca market data against the normalized ledger")
    parser.add_argument("--start", type=date.fromisoformat)
    parser.add_argument("--end", type=date.fromisoformat)
    parser.add_argument("--lookback-days", type=int, default=45)
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--sample-limit", type=int, default=25)
    parser.add_argument("--cohort", default=CURRENT_SURVIVORS_COHORT)
    parser.add_argument("--benchmark", default="SPY")
    parser.add_argument("--code-revision", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--fail-on-findings", action="store_true")
    arguments = parser.parse_args()
    if arguments.batch_size < 1 or arguments.sample_limit < 1 or arguments.lookback_days < 1:
        parser.error("--batch-size, --sample-limit, and --lookback-days must be positive")
    if bool(arguments.start) != bool(arguments.end):
        parser.error("--start and --end must be supplied together")
    if arguments.output.exists():
        raise DataQualityError(f"refusing to overwrite immutable reconciliation report: {arguments.output}")

    settings = _settings(arguments.env_file)
    settings.require_runtime_storage()
    settings.require_alpaca_access()
    assert settings.database_url and settings.alpaca_key_id and settings.alpaca_secret_key
    repository = PostgresReconciliationRepository(settings.database_url)
    try:
        end = arguments.end or repository.latest_benchmark_session(arguments.benchmark)
        start = arguments.start or end - timedelta(days=arguments.lookback_days - 1)
        if start > end:
            parser.error("--start must not be after --end")
        report = run_reconciliation(
            repository=repository,
            client=AlpacaClient(settings.alpaca_key_id, settings.alpaca_secret_key),
            cohort_code=arguments.cohort,
            benchmark_ticker=arguments.benchmark.upper(),
            start=start, end=end, batch_size=arguments.batch_size, sample_limit=arguments.sample_limit,
            code_revision=arguments.code_revision, progress=print,
        )
    finally:
        repository.close()
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        f"status={report['status']}; ledger_consistent={report['ledger_consistent']}; "
        f"actionable_findings={report['actionable_finding_count']}; output={arguments.output}"
    )
    if arguments.fail_on_findings and report["status"] != "clean":
        raise DataQualityError("market-data reconciliation reported findings; review the immutable report")


if __name__ == "__main__":
    main()
