"""Next-open, equal-weight rebalance selection and ledger construction."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Iterable, Literal

from .baseline import CompositeBaselineScore
from .quality import DataQualityError


TradeSide = Literal["buy", "sell"]


@dataclass(frozen=True, slots=True)
class RebalanceTarget:
    security_id: str
    target_weight: Decimal


@dataclass(frozen=True, slots=True)
class NextOpenPrice:
    security_id: str
    session_date: date
    open_price: Decimal


@dataclass(frozen=True, slots=True)
class PortfolioPosition:
    security_id: str
    quantity: Decimal


@dataclass(frozen=True, slots=True)
class PortfolioState:
    cash: Decimal
    positions: tuple[PortfolioPosition, ...]


@dataclass(frozen=True, slots=True)
class LedgerTrade:
    security_id: str
    side: TradeSide
    quantity: Decimal
    execution_price: Decimal
    notional: Decimal


@dataclass(frozen=True, slots=True)
class RebalanceLedger:
    formation_date: date
    execution_date: date
    starting_nav: Decimal
    ending_cash: Decimal
    positions: tuple[PortfolioPosition, ...]
    trades: tuple[LedgerTrade, ...]


def select_equal_weight_targets(
    scores: Iterable[CompositeBaselineScore], *, formation_date: date, portfolio_size: int = 20
) -> tuple[RebalanceTarget, ...]:
    """Select exactly the highest eligible baseline scores with equal weights."""
    if portfolio_size < 1:
        raise DataQualityError("portfolio_size must be positive")
    score_list = list(scores)
    if any(score.formation_date != formation_date for score in score_list):
        raise DataQualityError("all candidate scores must use the requested formation date")
    candidates = [score for score in score_list if score.eligible and score.normalized_score is not None]
    if len({score.security_id for score in candidates}) != len(candidates):
        raise DataQualityError("duplicate eligible baseline score")
    if len(candidates) < portfolio_size:
        raise DataQualityError(
            f"rebalance requires {portfolio_size} eligible scores; only {len(candidates)} are available"
        )
    candidates.sort(key=lambda score: (-score.normalized_score, score.security_id))
    weight = Decimal("1") / Decimal(portfolio_size)
    return tuple(RebalanceTarget(score.security_id, weight) for score in candidates[:portfolio_size])


def _open_price_index(
    prices: Iterable[NextOpenPrice], *, execution_date: date
) -> dict[str, Decimal]:
    index: dict[str, Decimal] = {}
    for price in prices:
        if price.session_date != execution_date:
            continue
        if price.security_id in index:
            raise DataQualityError(f"duplicate next-open price for {price.security_id}")
        if price.open_price <= 0:
            raise DataQualityError(f"next-open price must be positive for {price.security_id}")
        index[price.security_id] = price.open_price
    return index


def _position_index(positions: Iterable[PortfolioPosition]) -> dict[str, Decimal]:
    index: dict[str, Decimal] = {}
    for position in positions:
        if position.security_id in index:
            raise DataQualityError(f"duplicate portfolio position for {position.security_id}")
        if position.quantity < 0:
            raise DataQualityError(f"short position is outside the baseline scope: {position.security_id}")
        index[position.security_id] = position.quantity
    return index


def build_next_open_rebalance_ledger(
    prior_state: PortfolioState,
    targets: Iterable[RebalanceTarget],
    execution_opens: Iterable[NextOpenPrice],
    *,
    formation_date: date,
    execution_date: date,
) -> RebalanceLedger:
    """Sell every prior position then establish the selected portfolio at next open."""
    if execution_date <= formation_date:
        raise DataQualityError("execution date must be strictly after the formation date")
    if prior_state.cash < 0:
        raise DataQualityError("baseline portfolio cash cannot be negative")
    target_list = list(targets)
    if not target_list:
        raise DataQualityError("rebalance requires at least one target")
    target_ids = [target.security_id for target in target_list]
    if len(set(target_ids)) != len(target_ids):
        raise DataQualityError("rebalance targets must be unique")
    if any(target.target_weight <= 0 for target in target_list):
        raise DataQualityError("rebalance target weights must be positive")
    if sum((target.target_weight for target in target_list), Decimal("0")) != Decimal("1"):
        raise DataQualityError("rebalance target weights must sum exactly to one")
    prices = _open_price_index(execution_opens, execution_date=execution_date)
    positions = _position_index(prior_state.positions)
    required_prices = set(positions) | set(target_ids)
    missing_prices = required_prices - prices.keys()
    if missing_prices:
        raise DataQualityError(
            f"missing next-open price for: {', '.join(sorted(missing_prices))}"
        )
    starting_nav = prior_state.cash + sum(
        (quantity * prices[security_id] for security_id, quantity in positions.items()), Decimal("0")
    )
    trades: list[LedgerTrade] = []
    cash = prior_state.cash
    for security_id in sorted(positions):
        quantity = positions[security_id]
        if quantity == 0:
            continue
        notional = quantity * prices[security_id]
        trades.append(LedgerTrade(security_id, "sell", quantity, prices[security_id], notional))
        cash += notional
    new_positions: list[PortfolioPosition] = []
    for target in sorted(target_list, key=lambda item: item.security_id):
        notional = starting_nav * target.target_weight
        quantity = notional / prices[target.security_id]
        trades.append(LedgerTrade(target.security_id, "buy", quantity, prices[target.security_id], notional))
        cash -= notional
        new_positions.append(PortfolioPosition(target.security_id, quantity))
    return RebalanceLedger(
        formation_date,
        execution_date,
        starting_nav,
        cash,
        tuple(new_positions),
        tuple(trades),
    )
