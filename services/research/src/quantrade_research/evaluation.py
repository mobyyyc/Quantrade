"""Costs, liquidity gates, and benchmark-relative research performance metrics."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Iterable

from .quality import DataQualityError
from .rebalance import RebalanceLedger, RebalanceTarget


DEFAULT_ONE_WAY_COST_BPS = Decimal("5")
DEFAULT_LIQUIDITY_FLOOR = Decimal("10000000")
TRADING_DAYS_PER_YEAR = Decimal("252")


@dataclass(frozen=True, slots=True)
class LiquiditySnapshot:
    security_id: str
    formation_date: date
    median_dollar_volume: Decimal


@dataclass(frozen=True, slots=True)
class CostSensitivity:
    one_way_cost_bps: Decimal
    total_cost: Decimal
    post_cost_nav: Decimal


@dataclass(frozen=True, slots=True)
class RebalanceCostReport:
    starting_nav: Decimal
    gross_trade_notional: Decimal
    one_way_turnover: Decimal
    baseline: CostSensitivity
    sensitivities: tuple[CostSensitivity, ...]


@dataclass(frozen=True, slots=True)
class NavObservation:
    session_date: date
    portfolio_nav: Decimal
    benchmark_nav: Decimal


@dataclass(frozen=True, slots=True)
class PerformanceMetrics:
    observation_count: int
    portfolio_cumulative_return: Decimal
    benchmark_cumulative_return: Decimal
    benchmark_relative_return: Decimal
    portfolio_cagr: Decimal
    annualized_volatility: Decimal | None
    sharpe_ratio: Decimal | None
    sortino_ratio: Decimal | None
    maximum_drawdown: Decimal
    calmar_ratio: Decimal | None


def validate_rebalance_liquidity(
    targets: Iterable[RebalanceTarget],
    snapshots: Iterable[LiquiditySnapshot],
    *,
    formation_date: date,
    liquidity_floor: Decimal = DEFAULT_LIQUIDITY_FLOOR,
) -> None:
    """Require every selected target to meet the protocol's median-volume floor."""
    if liquidity_floor <= 0:
        raise DataQualityError("liquidity floor must be positive")
    target_ids = {target.security_id for target in targets}
    if not target_ids:
        raise DataQualityError("liquidity validation requires at least one target")
    indexed: dict[str, LiquiditySnapshot] = {}
    for snapshot in snapshots:
        if snapshot.security_id not in target_ids or snapshot.formation_date != formation_date:
            continue
        if snapshot.security_id in indexed:
            raise DataQualityError(f"duplicate liquidity snapshot for {snapshot.security_id}")
        if snapshot.median_dollar_volume < 0:
            raise DataQualityError(f"negative median dollar volume for {snapshot.security_id}")
        indexed[snapshot.security_id] = snapshot
    missing = target_ids - indexed.keys()
    if missing:
        raise DataQualityError(f"missing liquidity snapshot for: {', '.join(sorted(missing))}")
    illiquid = [
        security_id
        for security_id, snapshot in indexed.items()
        if snapshot.median_dollar_volume < liquidity_floor
    ]
    if illiquid:
        raise DataQualityError(
            f"liquidity floor not met for: {', '.join(sorted(illiquid))}"
        )


def rebalance_cost_report(
    ledger: RebalanceLedger,
    *,
    baseline_one_way_cost_bps: Decimal = DEFAULT_ONE_WAY_COST_BPS,
    sensitivity_bps: tuple[Decimal, ...] = (Decimal("1"), Decimal("10"), Decimal("20")),
) -> RebalanceCostReport:
    """Report one-way transaction costs without changing the cost-free ledger's trades."""
    if ledger.starting_nav <= 0:
        raise DataQualityError("starting NAV must be positive for cost reporting")
    if baseline_one_way_cost_bps < 0 or any(value < 0 for value in sensitivity_bps):
        raise DataQualityError("transaction costs cannot be negative")
    gross_trade_notional = sum((trade.notional for trade in ledger.trades), Decimal("0"))
    one_way_turnover = sum(
        (trade.notional for trade in ledger.trades if trade.side == "buy"), Decimal("0")
    ) / ledger.starting_nav

    def sensitivity(cost_bps: Decimal) -> CostSensitivity:
        total_cost = gross_trade_notional * cost_bps / Decimal("10000")
        return CostSensitivity(cost_bps, total_cost, ledger.starting_nav - total_cost)

    return RebalanceCostReport(
        ledger.starting_nav,
        gross_trade_notional,
        one_way_turnover,
        sensitivity(baseline_one_way_cost_bps),
        tuple(sensitivity(value) for value in sensitivity_bps),
    )


def _sample_standard_deviation(values: list[Decimal]) -> Decimal | None:
    if len(values) < 2:
        return None
    mean = sum(values, Decimal("0")) / Decimal(len(values))
    variance = sum(((value - mean) ** 2 for value in values), Decimal("0")) / Decimal(len(values) - 1)
    return variance.sqrt()


def calculate_performance_metrics(observations: Iterable[NavObservation]) -> PerformanceMetrics:
    """Calculate explicit portfolio and benchmark metrics using dated, positive NAVs."""
    ordered = sorted(observations, key=lambda item: item.session_date)
    if len(ordered) < 2:
        raise DataQualityError("performance metrics require at least two observations")
    if len({item.session_date for item in ordered}) != len(ordered):
        raise DataQualityError("performance observations must not duplicate a session date")
    if any(item.portfolio_nav <= 0 or item.benchmark_nav <= 0 for item in ordered):
        raise DataQualityError("portfolio and benchmark NAVs must be positive")
    portfolio_returns = [
        current.portfolio_nav / prior.portfolio_nav - Decimal("1")
        for prior, current in zip(ordered, ordered[1:])
    ]
    portfolio_cumulative_return = ordered[-1].portfolio_nav / ordered[0].portfolio_nav - Decimal("1")
    benchmark_cumulative_return = ordered[-1].benchmark_nav / ordered[0].benchmark_nav - Decimal("1")
    years = Decimal(len(portfolio_returns)) / TRADING_DAYS_PER_YEAR
    portfolio_cagr = ((Decimal("1") + portfolio_cumulative_return).ln() / years).exp() - Decimal("1")
    daily_volatility = _sample_standard_deviation(portfolio_returns)
    annualized_volatility = daily_volatility * TRADING_DAYS_PER_YEAR.sqrt() if daily_volatility is not None else None
    mean_return = sum(portfolio_returns, Decimal("0")) / Decimal(len(portfolio_returns))
    sharpe_ratio = (
        mean_return / daily_volatility * TRADING_DAYS_PER_YEAR.sqrt()
        if daily_volatility is not None and daily_volatility != 0
        else None
    )
    downside_returns = [min(value, Decimal("0")) for value in portfolio_returns]
    downside_deviation = (
        sum((value**2 for value in downside_returns), Decimal("0")) / Decimal(len(downside_returns))
    ).sqrt()
    sortino_ratio = (
        mean_return / downside_deviation * TRADING_DAYS_PER_YEAR.sqrt()
        if downside_deviation != 0
        else None
    )
    peak = ordered[0].portfolio_nav
    maximum_drawdown = Decimal("0")
    for observation in ordered:
        peak = max(peak, observation.portfolio_nav)
        maximum_drawdown = min(maximum_drawdown, observation.portfolio_nav / peak - Decimal("1"))
    calmar_ratio = portfolio_cagr / abs(maximum_drawdown) if maximum_drawdown != 0 else None
    return PerformanceMetrics(
        len(ordered), portfolio_cumulative_return, benchmark_cumulative_return,
        portfolio_cumulative_return - benchmark_cumulative_return, portfolio_cagr,
        annualized_volatility, sharpe_ratio, sortino_ratio, maximum_drawdown, calmar_ratio,
    )
