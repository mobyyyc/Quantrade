"""Deterministic next-open wealth accounting for Phase 9C labels."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from hashlib import sha256
import json
from typing import Iterable

from .quality import DataQualityError


LEDGER_RULE = "next_open_cash_dividend_split_wealth_v1"
PAPER_PORTFOLIO_LEDGER_RULE = "entry_open_checkpoint_close_cash_dividend_split_wealth_v1"
SPLIT_ACTIONS = frozenset({"forward_split", "reverse_split", "unit_split"})
CASH_ACTIONS = frozenset({"cash_dividend"})
NON_ECONOMIC_ACTIONS = frozenset({"name_change"})
COMPLEX_ACTIONS = frozenset({
    "stock_dividend", "spin_off", "cash_merger", "stock_merger",
    "stock_and_cash_merger", "redemption", "worthless_removal",
    "rights_distribution", "partial_call", "reorganization",
})
KNOWN_ACTIONS = SPLIT_ACTIONS | CASH_ACTIONS | NON_ECONOMIC_ACTIONS | COMPLEX_ACTIONS
# A large unexplained overnight open-to-open move is not "repaired" as a
# corporate action. It is conservatively withheld because the free action feed
# demonstrably omits some spin-offs. This may also withhold genuine event moves;
# that loss of coverage is preferable to inventing an adjustment.
# This catches extreme raw-price discontinuities before provider reconciliation.
# Lower discontinuities and ticker-identity collisions are caught by the strict
# total-return reconciliation performed by the portfolio outcome pipeline.
STRUCTURAL_JUMP_THRESHOLD = Decimal("0.15")


@dataclass(frozen=True, slots=True)
class WealthAction:
    action_id: str
    action_type: str
    effective_date: date | None
    process_date: date
    available_at: datetime
    cash_amount: Decimal | None = None
    ratio_numerator: Decimal | None = None
    ratio_denominator: Decimal | None = None
    currency: str | None = "USD"
    source_reference: str = ""

    @property
    def event_date(self) -> date | None:
        return self.effective_date


@dataclass(frozen=True, slots=True)
class WealthPriceMark:
    session_date: date
    open_price: Decimal
    available_at: datetime


@dataclass(frozen=True, slots=True)
class WealthLedgerResult:
    status: str
    entry_date: date
    exit_date: date
    entry_price: Decimal
    exit_price: Decimal
    wealth_return: Decimal | None
    ending_quantity: Decimal | None
    cash_distributions: Decimal | None
    action_ids: tuple[str, ...]
    data_cutoff_at: datetime | None
    unavailable_reason: str | None
    ledger_rule: str = LEDGER_RULE

    @property
    def digest(self) -> str:
        document = {
            "status": self.status,
            "entry_date": self.entry_date.isoformat(),
            "exit_date": self.exit_date.isoformat(),
            "entry_price": str(self.entry_price),
            "exit_price": str(self.exit_price),
            "wealth_return": str(self.wealth_return) if self.wealth_return is not None else None,
            "ending_quantity": str(self.ending_quantity) if self.ending_quantity is not None else None,
            "cash_distributions": str(self.cash_distributions) if self.cash_distributions is not None else None,
            "action_ids": self.action_ids,
            "data_cutoff_at": self.data_cutoff_at.isoformat() if self.data_cutoff_at else None,
            "unavailable_reason": self.unavailable_reason,
            "ledger_rule": self.ledger_rule,
        }
        return sha256(json.dumps(document, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class RelativeWealthResult:
    status: str
    security: WealthLedgerResult
    benchmark: WealthLedgerResult
    benchmark_relative_return: Decimal | None
    unavailable_reason: str | None = None


def _withheld(
    *, entry_date: date, exit_date: date, entry_price: Decimal, exit_price: Decimal,
    action_ids: tuple[str, ...], reason: str, ledger_rule: str = LEDGER_RULE,
) -> WealthLedgerResult:
    return WealthLedgerResult(
        "withheld", entry_date, exit_date, entry_price, exit_price,
        None, None, None, action_ids, None, reason, ledger_rule,
    )


def calculate_wealth_return(
    *, entry_date: date, exit_date: date, entry_price: Decimal, exit_price: Decimal,
    entry_available_at: datetime, exit_available_at: datetime,
    actions: Iterable[WealthAction], intermediate_prices: Iterable[WealthPriceMark] = (),
    ledger_rule: str = LEDGER_RULE,
) -> WealthLedgerResult:
    """Value one share bought at the entry mark and sold at the exit mark.

    Cash distributions remain cash and are not reinvested. An event on the entry
    date is excluded because the entry open is already ex-action. An event on
    the exit date is included because a holder from the prior session retains
    the entitlement and the exit open is already ex-action. Same-day splits are
    applied before same-day cash dividends.
    """
    if exit_date <= entry_date:
        raise DataQualityError("wealth-ledger exit date must follow entry date")
    if entry_price <= 0 or exit_price <= 0:
        raise DataQualityError("wealth-ledger prices must be positive")
    if entry_available_at.tzinfo is None or exit_available_at.tzinfo is None:
        raise DataQualityError("wealth-ledger price availability must include a UTC offset")
    action_list = tuple(actions)
    if any(action.available_at.tzinfo is None for action in action_list):
        raise DataQualityError("wealth-ledger action availability must include a UTC offset")
    relevant = tuple(
        action for action in action_list
        if entry_date < (action.event_date or action.process_date) <= exit_date
    )
    ids = [action.action_id for action in relevant]
    if any(not value for value in ids) or len(ids) != len(set(ids)):
        raise DataQualityError("wealth-ledger action ids must be non-empty and unique")
    unknown = sorted({action.action_type for action in relevant if action.action_type not in KNOWN_ACTIONS})
    if unknown:
        return _withheld(
            entry_date=entry_date, exit_date=exit_date, entry_price=entry_price,
            exit_price=exit_price, action_ids=tuple(sorted(ids)),
            reason=f"unknown corporate action type: {', '.join(unknown)}", ledger_rule=ledger_rule,
        )
    undated = sorted(action.action_id for action in relevant if action.event_date is None)
    if undated:
        return _withheld(
            entry_date=entry_date, exit_date=exit_date, entry_price=entry_price,
            exit_price=exit_price, action_ids=tuple(sorted(ids)),
            reason="corporate action has no effective date: " + ", ".join(undated), ledger_rule=ledger_rule,
        )
    complex_types = sorted({action.action_type for action in relevant if action.action_type in COMPLEX_ACTIONS})
    if complex_types:
        return _withheld(
            entry_date=entry_date, exit_date=exit_date, entry_price=entry_price,
            exit_price=exit_price, action_ids=tuple(sorted(ids)),
            reason="unresolved complex corporate action: " + ", ".join(complex_types), ledger_rule=ledger_rule,
        )
    price_path = tuple(sorted(intermediate_prices, key=lambda item: item.session_date))
    if price_path:
        if len({item.session_date for item in price_path}) != len(price_path):
            raise DataQualityError("wealth-ledger price path contains duplicate sessions")
        if any(item.open_price <= 0 for item in price_path):
            raise DataQualityError("wealth-ledger price path contains a non-positive mark")
        if any(item.available_at.tzinfo is None for item in price_path):
            raise DataQualityError("wealth-ledger price-path availability must include a UTC offset")
        splits_by_date: dict[date, Decimal] = {}
        for action in relevant:
            if action.action_type not in SPLIT_ACTIONS or action.event_date is None:
                continue
            if action.ratio_numerator is None or action.ratio_denominator is None:
                continue
            splits_by_date[action.event_date] = (
                splits_by_date.get(action.event_date, Decimal("1"))
                * action.ratio_numerator / action.ratio_denominator
            )
        for previous, current in zip(price_path, price_path[1:]):
            split_factor = splits_by_date.get(current.session_date, Decimal("1"))
            adjusted_jump = current.open_price * split_factor / previous.open_price - Decimal("1")
            if abs(adjusted_jump) > STRUCTURAL_JUMP_THRESHOLD:
                return _withheld(
                    entry_date=entry_date, exit_date=exit_date, entry_price=entry_price,
                    exit_price=exit_price, action_ids=tuple(sorted(ids)),
                    reason=(
                        f"unexplained structural price discontinuity on {current.session_date.isoformat()}: "
                        f"{adjusted_jump}"
                    ), ledger_rule=ledger_rule,
                )
    priority = {**{key: 0 for key in SPLIT_ACTIONS}, "cash_dividend": 1, "name_change": 2}
    ordered = sorted(relevant, key=lambda action: (action.event_date, priority[action.action_type], action.action_id))
    quantity = Decimal("1")
    cash = Decimal("0")
    cutoff = max(entry_available_at, exit_available_at)
    if price_path:
        cutoff = max(cutoff, *(item.available_at for item in price_path))
    applied: list[str] = []
    for action in ordered:
        cutoff = max(cutoff, action.available_at)
        if action.action_type in SPLIT_ACTIONS:
            if action.ratio_numerator is None or action.ratio_denominator is None:
                return _withheld(
                    entry_date=entry_date, exit_date=exit_date, entry_price=entry_price,
                    exit_price=exit_price, action_ids=tuple(sorted(ids)),
                    reason=f"split action {action.action_id} has no complete ratio", ledger_rule=ledger_rule,
                )
            if action.ratio_numerator <= 0 or action.ratio_denominator <= 0:
                raise DataQualityError("wealth-ledger split ratios must be positive")
            quantity *= action.ratio_numerator / action.ratio_denominator
        elif action.action_type in CASH_ACTIONS:
            if action.cash_amount is None or action.cash_amount < 0 or action.currency != "USD":
                return _withheld(
                    entry_date=entry_date, exit_date=exit_date, entry_price=entry_price,
                    exit_price=exit_price, action_ids=tuple(sorted(ids)),
                    reason=f"cash dividend {action.action_id} has invalid amount or currency", ledger_rule=ledger_rule,
                )
            cash += quantity * action.cash_amount
        applied.append(action.action_id)
    ending_wealth = quantity * exit_price + cash
    wealth_return = ending_wealth / entry_price - Decimal("1")
    return WealthLedgerResult(
        "completed", entry_date, exit_date, entry_price, exit_price,
        wealth_return, quantity, cash, tuple(applied), cutoff, None, ledger_rule,
    )


def calculate_relative_wealth_return(
    security: WealthLedgerResult, benchmark: WealthLedgerResult,
) -> RelativeWealthResult:
    if security.entry_date != benchmark.entry_date or security.exit_date != benchmark.exit_date:
        raise DataQualityError("security and benchmark wealth windows must match")
    if security.status != "completed" or benchmark.status != "completed":
        reasons = [
            result.unavailable_reason for result in (security, benchmark)
            if result.status != "completed" and result.unavailable_reason
        ]
        return RelativeWealthResult(
            "withheld", security, benchmark, None,
            "; ".join(reasons) or "security or benchmark wealth return is unavailable",
        )
    assert security.wealth_return is not None and benchmark.wealth_return is not None
    return RelativeWealthResult(
        "completed", security, benchmark,
        security.wealth_return - benchmark.wealth_return,
    )
