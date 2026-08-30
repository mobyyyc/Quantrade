"""Frozen raw-feature, ranking, and economic-family rules for Phase 9C."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from hashlib import sha256
import json
import math
from typing import Mapping, Sequence


FEATURE_RULE_VERSION = "phase_9c_weekly_feature_family_v1"
MAX_ACCOUNTING_STALENESS_DAYS = 450


@dataclass(frozen=True, slots=True)
class RawFeatureSpec:
    key: str
    family: str
    direction: int
    domain: str


RAW_FEATURE_SPECS = (
    RawFeatureSpec("momentum_12_1", "momentum_trend", 1, "market"),
    RawFeatureSpec("relative_strength_6m", "momentum_trend", 1, "market"),
    RawFeatureSpec("short_term_reversal_20d", "reversal", -1, "market"),
    RawFeatureSpec("book_to_market", "value", 1, "accounting"),
    RawFeatureSpec("earnings_yield_ttm", "value", 1, "accounting"),
    RawFeatureSpec("operating_cash_flow_yield_ttm", "value", 1, "accounting"),
    RawFeatureSpec("return_on_assets_ttm", "profitability_quality", 1, "accounting"),
    RawFeatureSpec("operating_cash_flow_profitability_ttm", "profitability_quality", 1, "accounting"),
    RawFeatureSpec("accrual_quality_ttm", "profitability_quality", -1, "accounting"),
    RawFeatureSpec("asset_growth_yoy", "investment_issuance", -1, "accounting"),
    RawFeatureSpec("net_share_issuance_yoy", "investment_issuance", -1, "accounting"),
    RawFeatureSpec("realized_volatility_60d", "risk", -1, "market"),
    RawFeatureSpec("idiosyncratic_volatility_60d", "risk", -1, "market"),
)
RAW_FEATURE_KEYS = tuple(item.key for item in RAW_FEATURE_SPECS)
FAMILY_MEMBERS = {
    family: tuple(item.key for item in RAW_FEATURE_SPECS if item.family == family)
    for family in dict.fromkeys(item.family for item in RAW_FEATURE_SPECS)
}
FAMILY_KEYS = tuple(FAMILY_MEMBERS)
MARKET_FAMILIES = frozenset({"momentum_trend", "reversal", "risk"})
ACCOUNTING_FAMILIES = frozenset({"value", "profitability_quality", "investment_issuance"})


@dataclass(frozen=True, slots=True)
class PriceBar:
    lineage_id: str
    security_id: str
    session_date: date
    close_price: Decimal
    available_at: datetime
    adjustment_basis: str


@dataclass(frozen=True, slots=True)
class RawFeatureCell:
    value: Decimal | None
    lineage: tuple[str, ...]
    exclusion: str | None = None

    @property
    def available(self) -> bool:
        return self.value is not None and self.exclusion is None

    def digest(self, feature_key: str) -> str:
        payload = {
            "feature_key": feature_key,
            "rule_version": FEATURE_RULE_VERSION,
            "value": str(self.value) if self.value is not None else None,
            "lineage": self.lineage,
            "exclusion": self.exclusion,
        }
        return sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class RankedFeatureCell:
    raw: RawFeatureCell
    centered_rank: Decimal


@dataclass(frozen=True, slots=True)
class FamilyCell:
    value: Decimal
    availability: Decimal
    informative: bool
    available_feature_count: int
    feature_count: int


def missing(reason: str) -> RawFeatureCell:
    return RawFeatureCell(None, (), reason)


def _window_token(bars: Sequence[PriceBar]) -> str:
    if not bars:
        raise ValueError("price lineage window cannot be empty")
    return (
        f"price_window:{bars[0].adjustment_basis}:{bars[0].security_id}:"
        f"{bars[0].session_date.isoformat()}:{bars[-1].session_date.isoformat()}:"
        f"{len(bars)}"
    )


def _returns(bars: Sequence[PriceBar]) -> list[float]:
    return [
        math.log(float(current.close_price / previous.close_price))
        for previous, current in zip(bars, bars[1:])
    ]


def _sample_volatility(returns: Sequence[float], *, fitted_parameters: int = 1) -> Decimal:
    if fitted_parameters < 0 or len(returns) <= fitted_parameters:
        raise ValueError("volatility requires more observations than fitted parameters")
    mean = sum(returns) / len(returns)
    variance = sum((item - mean) ** 2 for item in returns) / (len(returns) - fitted_parameters)
    return Decimal(str(math.sqrt(variance * 252)))


def market_feature_cells(
    stock_bars: Sequence[PriceBar], benchmark_bars: Sequence[PriceBar], *, formation_date: date,
) -> dict[str, RawFeatureCell]:
    """Calculate the six frozen market raw features for one formation."""
    result = {
        key: missing("missing_formation_price")
        for key in (
            "momentum_12_1", "relative_strength_6m", "short_term_reversal_20d",
            "realized_volatility_60d", "idiosyncratic_volatility_60d",
        )
    }
    if not stock_bars or stock_bars[-1].session_date != formation_date:
        return result
    if any(item.close_price <= 0 for item in stock_bars):
        return {key: missing("nonpositive_split_adjusted_price") for key in result}

    if len(stock_bars) >= 253:
        window = stock_bars[-253:]
        result["momentum_12_1"] = RawFeatureCell(
            window[-22].close_price / window[0].close_price - Decimal("1"),
            (_window_token((window[0], window[-22])),),
        )
    else:
        result["momentum_12_1"] = missing("insufficient_253_session_history")

    if len(stock_bars) >= 22:
        window = stock_bars[-22:-1]
        result["short_term_reversal_20d"] = RawFeatureCell(
            window[-1].close_price / window[0].close_price - Decimal("1"),
            (_window_token((window[0], window[-1])),),
        )
    else:
        result["short_term_reversal_20d"] = missing("insufficient_22_session_history")

    benchmark_by_date = {item.session_date: item for item in benchmark_bars}
    if len(stock_bars) >= 127:
        window = stock_bars[-127:]
        spy = [benchmark_by_date.get(item.session_date) for item in window]
        if all(spy):
            benchmark_window = tuple(item for item in spy if item is not None)
            value = (
                window[-1].close_price / window[0].close_price
                - benchmark_window[-1].close_price / benchmark_window[0].close_price
            )
            result["relative_strength_6m"] = RawFeatureCell(
                value, (_window_token((window[0], window[-1])), _window_token((benchmark_window[0], benchmark_window[-1]))),
            )
        else:
            result["relative_strength_6m"] = missing("mismatched_127_session_benchmark_history")
    else:
        result["relative_strength_6m"] = missing("insufficient_127_session_history")

    if len(stock_bars) >= 61:
        window = stock_bars[-61:]
        stock_returns = _returns(window)
        result["realized_volatility_60d"] = RawFeatureCell(
            _sample_volatility(stock_returns), (_window_token(window),),
        )
        spy = [benchmark_by_date.get(item.session_date) for item in window]
        if all(spy):
            benchmark_window = tuple(item for item in spy if item is not None)
            benchmark_returns = _returns(benchmark_window)
            benchmark_mean = sum(benchmark_returns) / len(benchmark_returns)
            stock_mean = sum(stock_returns) / len(stock_returns)
            benchmark_ss = sum((item - benchmark_mean) ** 2 for item in benchmark_returns)
            if benchmark_ss > 0:
                beta = sum(
                    (stock - stock_mean) * (benchmark - benchmark_mean)
                    for stock, benchmark in zip(stock_returns, benchmark_returns, strict=True)
                ) / benchmark_ss
                residuals = [
                    stock - stock_mean - beta * (benchmark - benchmark_mean)
                    for stock, benchmark in zip(stock_returns, benchmark_returns, strict=True)
                ]
                result["idiosyncratic_volatility_60d"] = RawFeatureCell(
                    _sample_volatility(residuals, fitted_parameters=2),
                    (_window_token(window), _window_token(benchmark_window)),
                )
            else:
                result["idiosyncratic_volatility_60d"] = missing("zero_benchmark_variance")
        else:
            result["idiosyncratic_volatility_60d"] = missing("mismatched_61_session_benchmark_history")
    else:
        result["realized_volatility_60d"] = missing("insufficient_61_session_history")
        result["idiosyncratic_volatility_60d"] = missing("insufficient_61_session_history")
    return result


def centered_cross_sectional_ranks(
    cells: Mapping[str, RawFeatureCell], *, direction: int,
) -> dict[str, RankedFeatureCell]:
    """Tie-aware market-wide ranks in [-1, 1], with missing values neutral at zero."""
    if direction not in {-1, 1}:
        raise ValueError("feature direction must be -1 or 1")
    available = sorted(
        ((security_id, cell) for security_id, cell in cells.items() if cell.available),
        key=lambda item: (item[1].value, item[0]),
    )
    ranks: dict[str, Decimal] = {}
    if len(available) == 1:
        ranks[available[0][0]] = Decimal("0")
    elif len(available) > 1:
        denominator = Decimal(len(available) - 1)
        position = 0
        while position < len(available):
            end = position
            while end + 1 < len(available) and available[end + 1][1].value == available[position][1].value:
                end += 1
            percentile = Decimal(position + end) / Decimal("2") / denominator
            centered = (percentile * Decimal("2") - Decimal("1")) * direction
            for security_id, _ in available[position:end + 1]:
                ranks[security_id] = centered
            position = end + 1
    return {
        security_id: RankedFeatureCell(cell, ranks.get(security_id, Decimal("0")))
        for security_id, cell in cells.items()
    }


def compose_families(
    ranked: Mapping[str, RankedFeatureCell],
) -> dict[str, FamilyCell]:
    result: dict[str, FamilyCell] = {}
    for family, members in FAMILY_MEMBERS.items():
        cells = [ranked[key] for key in members]
        available_count = sum(item.raw.available for item in cells)
        result[family] = FamilyCell(
            value=sum((item.centered_rank for item in cells), Decimal("0")) / Decimal(len(cells)),
            availability=Decimal(available_count) / Decimal(len(cells)),
            informative=available_count > 0,
            available_feature_count=available_count,
            feature_count=len(cells),
        )
    return result
