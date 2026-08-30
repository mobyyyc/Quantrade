"""Fail-closed point-in-time quarterly and TTM accounting primitives.

This module consumes facts already filtered by the unified SEC resolver. It
does not repair missing contexts, mix concepts, or substitute period-average
shares for an endpoint share count.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, timedelta
from decimal import Decimal
from hashlib import sha256
import json
from typing import Iterable, Sequence

from .sec_fact_resolver import ResolvedSecFact


ACCOUNTING_RULE_VERSION = "phase_9c_strict_quarterly_ttm_v1"
FLOW_FORMS = frozenset({"10-K", "10-K/A", "10-Q", "10-Q/A"})
FLOW_SLOTS = ("Q1", "Q2", "Q3", "FY")
FLOW_DURATION_DAYS = {
    "Q1": (70, 120),
    "Q2": (150, 220),
    "Q3": (230, 310),
    "FY": (320, 390),
}
QUARTER_DURATION_DAYS = (65, 120)
MAX_INTERQUARTER_GAP_DAYS = 7
NET_INCOME_CONCEPTS = ("NetIncomeLoss", "ProfitLoss")
OPERATING_CASH_FLOW_CONCEPT = "NetCashProvidedByUsedInOperatingActivities"
ENDPOINT_SHARE_CONCEPT = "EntityCommonStockSharesOutstanding"


@dataclass(frozen=True, slots=True)
class SelectedFactLineage:
    filing_fact_key: str
    accession_number: str
    submitted_form: str
    accepted_at: str
    available_at: str
    taxonomy: str
    concept: str
    unit: str
    period_start: str | None
    period_end: str
    fiscal_year: int | None
    fiscal_period: str | None
    source_reference: str
    observation_hash: str
    availability_rule: str

    @classmethod
    def from_fact(cls, fact: ResolvedSecFact) -> "SelectedFactLineage":
        return cls(
            filing_fact_key=fact.filing_fact_key,
            accession_number=fact.accession_number,
            submitted_form=fact.submitted_form,
            accepted_at=fact.accepted_at.isoformat(),
            available_at=fact.available_at.isoformat(),
            taxonomy=fact.taxonomy,
            concept=fact.concept,
            unit=fact.unit,
            period_start=fact.period_start.isoformat() if fact.period_start else None,
            period_end=fact.period_end.isoformat(),
            fiscal_year=fact.fiscal_year,
            fiscal_period=fact.fiscal_period,
            source_reference=fact.source_reference,
            observation_hash=fact.effective_observation_hash,
            availability_rule=fact.availability_rule,
        )


@dataclass(frozen=True, slots=True)
class AccountingValue:
    value: Decimal | None
    unit: str | None
    period_start: date | None
    period_end: date | None
    concept: str | None
    operation: str
    lineage: tuple[SelectedFactLineage, ...]
    exclusion: str | None = None
    rule_version: str = ACCOUNTING_RULE_VERSION

    @property
    def available(self) -> bool:
        return self.value is not None and self.exclusion is None

    def digest(self) -> str:
        payload = {
            "value": str(self.value) if self.value is not None else None,
            "unit": self.unit,
            "period_start": self.period_start.isoformat() if self.period_start else None,
            "period_end": self.period_end.isoformat() if self.period_end else None,
            "concept": self.concept,
            "operation": self.operation,
            "lineage": [asdict(item) for item in self.lineage],
            "exclusion": self.exclusion,
            "rule_version": self.rule_version,
        }
        return sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _excluded(reason: str, *, operation: str) -> AccountingValue:
    return AccountingValue(None, None, None, None, None, operation, (), reason)


def _canonical_form(fact: ResolvedSecFact) -> str:
    return fact.submitted_form.strip().upper()


def _latest_unambiguous(facts: Sequence[ResolvedSecFact]) -> ResolvedSecFact | None:
    if not facts:
        return None
    ordered = sorted(
        facts,
        key=lambda item: (item.available_at, item.accepted_at, item.is_amendment, item.accession_number, item.lineage_key),
    )
    latest = ordered[-1]
    tied = [
        item for item in ordered
        if item.available_at == latest.available_at and item.accepted_at == latest.accepted_at
    ]
    if len({item.value for item in tied}) > 1:
        return None
    return latest


def _valid_flow_fact(fact: ResolvedSecFact, *, concept: str) -> bool:
    if (
        fact.taxonomy != "us-gaap"
        or fact.concept != concept
        or fact.unit != "USD"
        or fact.period_start is None
        or fact.fiscal_period not in FLOW_SLOTS
        or _canonical_form(fact) not in FLOW_FORMS
    ):
        return False
    low, high = FLOW_DURATION_DAYS[fact.fiscal_period]
    return low <= (fact.period_end - fact.period_start).days <= high


def standalone_quarters(
    facts: Iterable[ResolvedSecFact], *, concept: str,
) -> tuple[AccountingValue, ...]:
    """Reconstruct standalone quarters from compatible YTD/FY chains."""
    candidates = [fact for fact in facts if _valid_flow_fact(fact, concept=concept)]
    by_cycle: dict[tuple[str, str, date], dict[str, list[ResolvedSecFact]]] = {}
    for fact in candidates:
        key = (fact.security_id, fact.unit, fact.period_start)  # type: ignore[arg-type]
        by_cycle.setdefault(key, {}).setdefault(fact.fiscal_period or "", []).append(fact)

    candidates_by_period: dict[tuple[date, date], list[AccountingValue]] = {}
    for (_security_id, unit, fiscal_start), slots in sorted(by_cycle.items()):
        q1 = _latest_unambiguous([item for item in slots.get("Q1", ()) if item.fiscal_year is not None])
        if q1 is not None:
            value = AccountingValue(
                q1.value, unit, fiscal_start, q1.period_end, concept, "Q1=Q1_YTD",
                (SelectedFactLineage.from_fact(q1),),
            )
            candidates_by_period.setdefault((fiscal_start, q1.period_end), []).append(value)

        for prior_slot, slot, label in (
            ("Q1", "Q2", "Q2=H1_YTD-Q1_YTD"),
            ("Q2", "Q3", "Q3=9M_YTD-H1_YTD"),
            ("Q3", "FY", "Q4=FY-9M_YTD"),
        ):
            fiscal_years = sorted({
                item.fiscal_year for item in (*slots.get(prior_slot, ()), *slots.get(slot, ()))
                if item.fiscal_year is not None
            })
            for fiscal_year in fiscal_years:
                prior = _latest_unambiguous([
                    item for item in slots.get(prior_slot, ()) if item.fiscal_year == fiscal_year
                ])
                current = _latest_unambiguous([
                    item for item in slots.get(slot, ()) if item.fiscal_year == fiscal_year
                ])
                if prior is None or current is None:
                    continue
                standalone_start = prior.period_end + timedelta(days=1)
                duration = (current.period_end - standalone_start).days
                if not QUARTER_DURATION_DAYS[0] <= duration <= QUARTER_DURATION_DAYS[1]:
                    continue
                value = AccountingValue(
                    current.value - prior.value,
                    unit,
                    standalone_start,
                    current.period_end,
                    concept,
                    label,
                    (SelectedFactLineage.from_fact(prior), SelectedFactLineage.from_fact(current)),
                )
                candidates_by_period.setdefault((standalone_start, current.period_end), []).append(value)

    results: list[AccountingValue] = []
    for values in candidates_by_period.values():
        ordered = sorted(
            values,
            key=lambda item: (
                max(line.available_at for line in item.lineage),
                tuple(line.observation_hash for line in item.lineage),
            ),
        )
        latest = ordered[-1]
        latest_at = max(line.available_at for line in latest.lineage)
        tied = [item for item in ordered if max(line.available_at for line in item.lineage) == latest_at]
        if len({item.value for item in tied}) > 1:
            continue
        results.append(latest)
    return tuple(sorted(results, key=lambda item: (item.period_end or date.min, item.operation, item.digest())))


def true_ttm(
    facts: Iterable[ResolvedSecFact], *, concepts: Sequence[str], formation_date: date,
) -> AccountingValue:
    """Return the latest four consecutive standalone quarters for one concept."""
    source = tuple(facts)
    for concept in concepts:
        quarters = [
            item for item in standalone_quarters(source, concept=concept)
            if item.available and item.period_end is not None and item.period_end <= formation_date
        ]
        if len(quarters) < 4:
            continue
        selected = quarters[-4:]
        consecutive = all(
            current.period_start is not None
            and previous.period_end is not None
            and 0 <= (current.period_start - previous.period_end).days - 1 <= MAX_INTERQUARTER_GAP_DAYS
            for previous, current in zip(selected, selected[1:])
        )
        if not consecutive or len({item.unit for item in selected}) != 1:
            continue
        lineage = tuple(line for item in selected for line in item.lineage)
        return AccountingValue(
            sum((item.value for item in selected if item.value is not None), Decimal("0")),
            selected[0].unit,
            selected[0].period_start,
            selected[-1].period_end,
            concept,
            "TTM=sum(latest_4_standalone_quarters)",
            lineage,
        )
    return _excluded("missing_four_consecutive_eligible_standalone_quarters", operation="TTM")


def latest_endpoint(
    facts: Iterable[ResolvedSecFact], *, concepts: Sequence[str], taxonomy: str,
    unit: str, formation_date: date, require_positive: bool = False,
) -> AccountingValue:
    """Select a dated instant fact, failing closed on conflicting latest context."""
    for concept in concepts:
        candidates = [
            fact for fact in facts
            if fact.taxonomy == taxonomy
            and fact.concept == concept
            and fact.unit == unit
            and fact.period_start is None
            and fact.period_end <= formation_date
            and _canonical_form(fact) in FLOW_FORMS
        ]
        if not candidates:
            continue
        latest_period = max(item.period_end for item in candidates)
        chosen = _latest_unambiguous([item for item in candidates if item.period_end == latest_period])
        if chosen is None:
            return _excluded("ambiguous_latest_endpoint_context", operation="latest_endpoint")
        if require_positive and chosen.value <= 0:
            return _excluded("nonpositive_latest_endpoint", operation="latest_endpoint")
        return AccountingValue(
            chosen.value, unit, chosen.period_end, chosen.period_end, concept, "latest_endpoint",
            (SelectedFactLineage.from_fact(chosen),),
        )
    return _excluded("missing_eligible_endpoint", operation="latest_endpoint")


def endpoint_shares(facts: Iterable[ResolvedSecFact], *, formation_date: date) -> AccountingValue:
    """Resolve primary shares without a weighted-average fallback."""
    return latest_endpoint(
        facts,
        concepts=(ENDPOINT_SHARE_CONCEPT,),
        taxonomy="dei",
        unit="shares",
        formation_date=formation_date,
        require_positive=True,
    )
