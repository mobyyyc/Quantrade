"""Coverage reporting for the free historical-market research lane."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime
import json
from pathlib import Path
from typing import Any

from .historical_cohorts import CURRENT_SURVIVORS_COHORT
from .historical_market_backfill import (
    FREE_TRACK_HOLDOUT_END_DATE,
    FREE_TRACK_START_DATE,
    HISTORICAL_BENCHMARK_RULE_VERSION,
    HISTORICAL_EOD_RULE_KEY,
    HISTORICAL_MARKET_RULE_VERSION,
)


@dataclass(frozen=True, slots=True)
class BasisCoverage:
    adjustment_basis: str
    row_count: int
    session_count: int
    company_count: int
    first_session: date | None
    last_session: date | None
    max_companies_per_benchmark_session: int
    missing_company_sessions: int


@dataclass(frozen=True, slots=True)
class FundamentalCoverage:
    company_count: int
    companies_with_filing: int
    companies_with_facts: int
    companies_with_pre_start_filing: int
    companies_with_pre_start_facts: int
    filing_count: int
    fact_count: int
    first_accepted_at: datetime | None
    last_accepted_at: datetime | None
    availability_mismatch_count: int


@dataclass(frozen=True, slots=True)
class HistoricalMarketCoverageReport:
    generated_at: datetime
    cohort_code: str
    requested_start: date
    requested_end: date
    cohort_company_count: int
    stock_coverage: tuple[BasisCoverage, ...]
    benchmark_coverage: tuple[BasisCoverage, ...]
    excluded_cohort_listings: tuple[str, ...]
    incorrect_stock_availability_count: int
    incorrect_benchmark_availability_count: int
    warnings: tuple[str, ...]
    fundamental_coverage: FundamentalCoverage | None = None

    def to_json(self) -> str:
        def convert(value: Any) -> Any:
            if isinstance(value, (date, datetime)):
                return value.isoformat()
            if isinstance(value, tuple):
                return [convert(item) for item in value]
            if isinstance(value, dict):
                return {key: convert(item) for key, item in value.items()}
            return value

        return json.dumps(convert(asdict(self)), indent=2, sort_keys=True) + "\n"


def coverage_warnings(
    *, requested_start: date, stock_coverage: tuple[BasisCoverage, ...],
    benchmark_coverage: tuple[BasisCoverage, ...], excluded_listings: tuple[str, ...],
    fundamental_coverage: FundamentalCoverage | None = None,
) -> tuple[str, ...]:
    warnings = [
        "Tier B only: this is a fixed current-survivors cohort, not dated historical S&P 500 membership.",
        "Sector grouping is current/static and is not point-in-time verified.",
        "Do not describe a model trained on this lane as historically unbiased or use it for public performance claims.",
    ]
    earliest = [coverage.first_session for coverage in (*stock_coverage, *benchmark_coverage) if coverage.first_session]
    if earliest and min(earliest) > requested_start:
        warnings.append(
            "Provider coverage begins after the requested backfill start; omitted earlier sessions are retained as exclusions."
        )
    if any(coverage.missing_company_sessions > 0 for coverage in stock_coverage):
        warnings.append(
            "Provider stock coverage is incomplete relative to benchmark sessions; examples without complete inputs must be withheld."
        )
    if excluded_listings:
        warnings.append("One or more fixed-cohort listings returned no historical bars and are excluded from usable examples.")
    if fundamental_coverage and fundamental_coverage.companies_with_pre_start_facts < fundamental_coverage.company_count:
        warnings.append(
            "SEC fundamentals are unavailable before the requested start for some cohort names; "
            "early examples must be withheld until each name has eligible facts."
        )
    return tuple(warnings)


class PostgresHistoricalMarketCoverageRepository:
    def __init__(self, database_url: str) -> None:
        try:
            import psycopg
        except ImportError as error:  # pragma: no cover
            raise RuntimeError("Install quantrade-research dependencies before coverage reporting") from error
        self._connection = psycopg.connect(database_url)

    def close(self) -> None:
        self._connection.close()

    def build_report(self, *, cohort_code: str, requested_start: date, requested_end: date) -> HistoricalMarketCoverageReport:
        with self._connection.cursor() as cursor:
            cursor.execute(
                """SELECT COUNT(*) FROM quantrade.research_cohort_memberships membership
                   JOIN quantrade.research_cohorts cohort
                     ON cohort.research_cohort_id = membership.research_cohort_id
                   WHERE cohort.cohort_code = %s""",
                (cohort_code,),
            )
            cohort_count = int(cursor.fetchone()[0])
            if cohort_count == 0:
                raise ValueError(f"no historical research cohort exists for {cohort_code}")

            cursor.execute(
                """SELECT bar.adjustment_basis, COUNT(*), COUNT(DISTINCT bar.session_date),
                          COUNT(DISTINCT bar.security_id), MIN(bar.session_date), MAX(bar.session_date)
                   FROM quantrade.daily_price_bars bar
                   JOIN quantrade.availability_rules rule ON rule.availability_rule_id = bar.availability_rule_id
                   WHERE rule.rule_key = %s AND rule.rule_version = %s AND rule.data_domain = 'market_bar'
                     AND bar.session_date BETWEEN %s AND %s
                   GROUP BY bar.adjustment_basis ORDER BY bar.adjustment_basis""",
                (HISTORICAL_EOD_RULE_KEY, HISTORICAL_MARKET_RULE_VERSION, requested_start, requested_end),
            )
            stock_rows = tuple(cursor.fetchall())

            cursor.execute(
                """SELECT bar.adjustment_basis, COUNT(*), COUNT(DISTINCT bar.session_date),
                          1, MIN(bar.session_date), MAX(bar.session_date)
                   FROM quantrade.benchmark_daily_price_bars bar
                   JOIN quantrade.availability_rules rule ON rule.availability_rule_id = bar.availability_rule_id
                   WHERE rule.rule_key = %s AND rule.rule_version = %s AND rule.data_domain = 'benchmark_bar'
                     AND bar.session_date BETWEEN %s AND %s
                   GROUP BY bar.adjustment_basis ORDER BY bar.adjustment_basis""",
                (HISTORICAL_EOD_RULE_KEY, HISTORICAL_BENCHMARK_RULE_VERSION, requested_start, requested_end),
            )
            benchmark_rows = tuple(cursor.fetchall())

            cursor.execute(
                """WITH stock AS (
                         SELECT bar.adjustment_basis, bar.session_date, bar.security_id
                         FROM quantrade.daily_price_bars bar
                         JOIN quantrade.availability_rules rule ON rule.availability_rule_id = bar.availability_rule_id
                         WHERE rule.rule_key = %s AND rule.rule_version = %s AND rule.data_domain = 'market_bar'
                           AND bar.session_date BETWEEN %s AND %s
                     ), benchmark_sessions AS (
                         SELECT bar.adjustment_basis, bar.session_date
                         FROM quantrade.benchmark_daily_price_bars bar
                         JOIN quantrade.availability_rules rule ON rule.availability_rule_id = bar.availability_rule_id
                         WHERE rule.rule_key = %s AND rule.rule_version = %s AND rule.data_domain = 'benchmark_bar'
                           AND bar.session_date BETWEEN %s AND %s
                     ), per_session AS (
                         SELECT benchmark_sessions.adjustment_basis, benchmark_sessions.session_date,
                                COUNT(stock.security_id)::integer AS company_count
                         FROM benchmark_sessions
                         LEFT JOIN stock ON stock.adjustment_basis = benchmark_sessions.adjustment_basis
                           AND stock.session_date = benchmark_sessions.session_date
                         GROUP BY benchmark_sessions.adjustment_basis, benchmark_sessions.session_date
                     )
                     SELECT adjustment_basis, MAX(company_count)::integer, SUM(company_count)::integer
                     FROM per_session GROUP BY adjustment_basis""",
                (HISTORICAL_EOD_RULE_KEY, HISTORICAL_MARKET_RULE_VERSION, requested_start, requested_end,
                 HISTORICAL_EOD_RULE_KEY, HISTORICAL_BENCHMARK_RULE_VERSION, requested_start, requested_end),
            )
            overlap = {str(row[0]): (int(row[1]), int(row[2])) for row in cursor.fetchall()}
            stock_coverage = tuple(
                BasisCoverage(
                    str(row[0]), int(row[1]), int(row[2]), int(row[3]), row[4], row[5],
                    overlap.get(str(row[0]), (0, 0))[0],
                    int(row[2]) * int(row[3]) - overlap.get(str(row[0]), (0, 0))[1],
                )
                for row in stock_rows
            )
            benchmark_coverage = tuple(
                BasisCoverage(str(row[0]), int(row[1]), int(row[2]), int(row[3]), row[4], row[5], 1, 0)
                for row in benchmark_rows
            )

            cursor.execute(
                """WITH cohort AS (
                         SELECT membership.security_id
                         FROM quantrade.research_cohort_memberships membership
                         JOIN quantrade.research_cohorts cohort
                           ON cohort.research_cohort_id = membership.research_cohort_id
                         WHERE cohort.cohort_code = %s
                     ), historical AS (
                         SELECT DISTINCT bar.security_id
                         FROM quantrade.daily_price_bars bar
                         JOIN quantrade.availability_rules rule ON rule.availability_rule_id = bar.availability_rule_id
                         WHERE rule.rule_key = %s AND rule.rule_version = %s AND rule.data_domain = 'market_bar'
                           AND bar.session_date BETWEEN %s AND %s
                     )
                     SELECT DISTINCT listing.ticker
                     FROM cohort
                     JOIN quantrade.listings listing ON listing.security_id = cohort.security_id AND listing.valid_to IS NULL
                     LEFT JOIN historical ON historical.security_id = cohort.security_id
                     WHERE historical.security_id IS NULL
                     ORDER BY listing.ticker""",
                (cohort_code, HISTORICAL_EOD_RULE_KEY, HISTORICAL_MARKET_RULE_VERSION, requested_start, requested_end),
            )
            excluded = tuple(str(row[0]) for row in cursor.fetchall())

            cursor.execute(
                """SELECT COUNT(*)
                   FROM quantrade.daily_price_bars bar
                   JOIN quantrade.availability_rules rule ON rule.availability_rule_id = bar.availability_rule_id
                   WHERE rule.rule_key = %s AND rule.rule_version = %s AND rule.data_domain = 'market_bar'
                     AND bar.session_date BETWEEN %s AND %s
                     AND bar.available_at <> ((bar.session_date::timestamp + time '18:00') AT TIME ZONE 'America/Toronto')""",
                (HISTORICAL_EOD_RULE_KEY, HISTORICAL_MARKET_RULE_VERSION, requested_start, requested_end),
            )
            incorrect_stock_availability = int(cursor.fetchone()[0])
            cursor.execute(
                """SELECT COUNT(*)
                   FROM quantrade.benchmark_daily_price_bars bar
                   JOIN quantrade.availability_rules rule ON rule.availability_rule_id = bar.availability_rule_id
                   WHERE rule.rule_key = %s AND rule.rule_version = %s AND rule.data_domain = 'benchmark_bar'
                     AND bar.session_date BETWEEN %s AND %s
                     AND bar.available_at <> ((bar.session_date::timestamp + time '18:00') AT TIME ZONE 'America/Toronto')""",
                (HISTORICAL_EOD_RULE_KEY, HISTORICAL_BENCHMARK_RULE_VERSION, requested_start, requested_end),
            )
            incorrect_benchmark_availability = int(cursor.fetchone()[0])

            cursor.execute(
                """WITH cohort AS (
                         SELECT membership.security_id
                         FROM quantrade.research_cohort_memberships membership
                         JOIN quantrade.research_cohorts cohort
                           ON cohort.research_cohort_id = membership.research_cohort_id
                         WHERE cohort.cohort_code = %s
                     ), scoped_filings AS (
                         SELECT filing.*
                         FROM quantrade.filings filing
                         JOIN cohort ON cohort.security_id = filing.security_id
                         WHERE filing.accepted_at <= (%s::date + interval '1 day')
                     ), scoped_facts AS (
                         SELECT fact.*
                         FROM quantrade.filing_facts fact
                         JOIN scoped_filings filing ON filing.filing_id = fact.filing_id
                     )
                     SELECT
                       (SELECT COUNT(*) FROM cohort),
                       (SELECT COUNT(DISTINCT security_id) FROM scoped_filings),
                       (SELECT COUNT(DISTINCT security_id) FROM scoped_facts),
                       (SELECT COUNT(DISTINCT security_id) FROM scoped_filings WHERE accepted_at < %s::date),
                       (SELECT COUNT(DISTINCT fact.security_id) FROM scoped_facts fact
                          JOIN scoped_filings filing ON filing.filing_id = fact.filing_id
                         WHERE filing.accepted_at < %s::date),
                       (SELECT COUNT(*) FROM scoped_filings),
                       (SELECT COUNT(*) FROM scoped_facts),
                       (SELECT MIN(accepted_at) FROM scoped_filings),
                       (SELECT MAX(accepted_at) FROM scoped_filings),
                       (SELECT COUNT(*) FROM scoped_facts fact
                          JOIN scoped_filings filing ON filing.filing_id = fact.filing_id
                         WHERE fact.available_at <> filing.accepted_at)""",
                (cohort_code, requested_end, requested_start, requested_start),
            )
            fundamental_row = cursor.fetchone()
            fundamental_coverage = FundamentalCoverage(
                company_count=int(fundamental_row[0]), companies_with_filing=int(fundamental_row[1]),
                companies_with_facts=int(fundamental_row[2]), companies_with_pre_start_filing=int(fundamental_row[3]),
                companies_with_pre_start_facts=int(fundamental_row[4]), filing_count=int(fundamental_row[5]),
                fact_count=int(fundamental_row[6]), first_accepted_at=fundamental_row[7],
                last_accepted_at=fundamental_row[8], availability_mismatch_count=int(fundamental_row[9]),
            )

        return HistoricalMarketCoverageReport(
            generated_at=datetime.now().astimezone(), cohort_code=cohort_code,
            requested_start=requested_start, requested_end=requested_end,
            cohort_company_count=cohort_count, stock_coverage=stock_coverage,
            benchmark_coverage=benchmark_coverage, excluded_cohort_listings=excluded,
            incorrect_stock_availability_count=incorrect_stock_availability,
            incorrect_benchmark_availability_count=incorrect_benchmark_availability,
            fundamental_coverage=fundamental_coverage,
            warnings=coverage_warnings(
                requested_start=requested_start, stock_coverage=stock_coverage,
                benchmark_coverage=benchmark_coverage, excluded_listings=excluded,
                fundamental_coverage=fundamental_coverage,
            ),
        )


def main() -> None:
    import argparse
    from .score_run import _settings

    parser = argparse.ArgumentParser(description="Write a Tier-B historical market coverage report")
    parser.add_argument("--start", type=date.fromisoformat, default=FREE_TRACK_START_DATE)
    parser.add_argument("--end", type=date.fromisoformat, default=FREE_TRACK_HOLDOUT_END_DATE)
    parser.add_argument("--cohort", default=CURRENT_SURVIVORS_COHORT)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    arguments = parser.parse_args()
    settings = _settings(arguments.env_file)
    repository = PostgresHistoricalMarketCoverageRepository(settings.database_url)
    try:
        report = repository.build_report(
            cohort_code=arguments.cohort, requested_start=arguments.start, requested_end=arguments.end,
        )
    finally:
        repository.close()
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(report.to_json(), encoding="utf-8")
    print(arguments.output)


if __name__ == "__main__":  # pragma: no cover
    main()
