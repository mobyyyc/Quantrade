"""Versioned, immutable definitions for research features."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal
from hashlib import sha256
import json
import re
from typing import Literal


FeatureFamily = Literal["momentum", "value", "profitability", "risk", "liquidity"]
FeatureDirection = Literal["higher_is_better", "lower_is_better"]

_FEATURE_KEY = re.compile(r"^[a-z][a-z0-9_]*$")
_FAMILIES = frozenset({"momentum", "value", "profitability", "risk", "liquidity"})
_DIRECTIONS = frozenset({"higher_is_better", "lower_is_better"})


class FeatureRegistryError(ValueError):
    """Raised when a feature definition cannot be registered safely."""


@dataclass(frozen=True, slots=True)
class FeatureDefinition:
    """The complete, immutable meaning of one versioned feature."""

    key: str
    version: str
    family: FeatureFamily
    direction: FeatureDirection
    display_name: str
    description: str
    formula: str
    required_inputs: tuple[str, ...]
    as_of_rule: str

    def __post_init__(self) -> None:
        if not _FEATURE_KEY.fullmatch(self.key):
            raise FeatureRegistryError("feature key must be lowercase snake_case")
        if not self.version.strip():
            raise FeatureRegistryError("feature version is required")
        if self.family not in _FAMILIES:
            raise FeatureRegistryError(f"unsupported feature family: {self.family}")
        if self.direction not in _DIRECTIONS:
            raise FeatureRegistryError(f"unsupported feature direction: {self.direction}")
        for field_name in ("display_name", "description", "formula", "as_of_rule"):
            if not getattr(self, field_name).strip():
                raise FeatureRegistryError(f"{field_name} is required")
        if not self.required_inputs or any(not item.strip() for item in self.required_inputs):
            raise FeatureRegistryError("at least one non-empty required input is required")
        if len(set(self.required_inputs)) != len(self.required_inputs):
            raise FeatureRegistryError("required inputs must not contain duplicates")

    def canonical_payload(self) -> dict[str, object]:
        """Return the field order used for reproducible definition hashes."""
        return asdict(self)

    @property
    def definition_hash(self) -> str:
        payload = json.dumps(
            self.canonical_payload(), separators=(",", ":"), sort_keys=True
        ).encode("utf-8")
        return sha256(payload).hexdigest()


@dataclass(frozen=True, slots=True)
class FeatureValue:
    """A calculated, versioned feature value for one formation date."""

    security_id: str
    formation_date: date
    feature_key: str
    feature_version: str
    definition_hash: str
    value: Decimal


class FeatureRegistry:
    """In-memory registry that prevents definition replacement or ambiguity."""

    def __init__(self, definitions: tuple[FeatureDefinition, ...] = ()) -> None:
        self._definitions: dict[tuple[str, str], FeatureDefinition] = {}
        for definition in definitions:
            self.register(definition)

    def register(self, definition: FeatureDefinition) -> None:
        identity = (definition.key, definition.version)
        if identity in self._definitions:
            raise FeatureRegistryError(
                f"feature definition already registered: {definition.key}@{definition.version}"
            )
        self._definitions[identity] = definition

    def get(self, key: str, version: str) -> FeatureDefinition:
        try:
            return self._definitions[(key, version)]
        except KeyError as exc:
            raise FeatureRegistryError(f"unknown feature definition: {key}@{version}") from exc

    def definitions(self) -> tuple[FeatureDefinition, ...]:
        return tuple(self._definitions[key] for key in sorted(self._definitions))

    @property
    def registry_hash(self) -> str:
        payload = [
            {**definition.canonical_payload(), "definition_hash": definition.definition_hash}
            for definition in self.definitions()
        ]
        return sha256(
            json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
        ).hexdigest()


BASELINE_FEATURE_DEFINITIONS: tuple[FeatureDefinition, ...] = (
    FeatureDefinition(
        key="momentum_12_1",
        version="v1",
        family="momentum",
        direction="higher_is_better",
        display_name="12-1 month momentum",
        description="Split-adjusted price momentum that omits the most recent trading month.",
        formula="C(t-21) / C(t-252) - 1, using split-adjusted closes.",
        required_inputs=("daily_price_bars:split_adjusted",),
        as_of_rule="Use only completed regular sessions with available_at at or before decision_at; t is the formation session.",
    ),
    FeatureDefinition(
        key="relative_strength_6m",
        version="v1",
        family="momentum",
        direction="higher_is_better",
        display_name="6 month relative strength",
        description="Six-month split-adjusted price return less the benchmark return over the same sessions.",
        formula="[C_i(t) / C_i(t-126) - 1] - [C_b(t) / C_b(t-126) - 1].",
        required_inputs=("daily_price_bars:split_adjusted", "benchmark_price_bars:split_adjusted"),
        as_of_rule="Use only sessions and benchmark observations available at or before decision_at; t is the formation session.",
    ),
    FeatureDefinition(
        key="earnings_yield_ttm",
        version="v2",
        family="value",
        direction="higher_is_better",
        display_name="Trailing earnings yield",
        description="Trailing-twelve-month net income relative to market capitalization.",
        formula="TTM net income / (split-adjusted close × shares outstanding).",
        required_inputs=("filing_facts:us-gaap:NetIncomeLoss|ProfitLoss", "filing_facts:dei:EntityCommonStockSharesOutstanding", "daily_price_bars:split_adjusted"),
        as_of_rule="Use only an annual SEC NetIncomeLoss fact or its standard ProfitLoss fallback whose available_at and price session are at or before decision_at; never infer an unfiled quarter.",
    ),
    FeatureDefinition(
        key="return_on_assets_ttm",
        version="v2",
        family="profitability",
        direction="higher_is_better",
        display_name="Trailing return on assets",
        description="Trailing net income scaled by average total assets.",
        formula="TTM net income / average(beginning total assets, ending total assets).",
        required_inputs=("filing_facts:us-gaap:NetIncomeLoss|ProfitLoss", "filing_facts:us-gaap:Assets"),
        as_of_rule="Use only an annual SEC NetIncomeLoss fact or its standard ProfitLoss fallback and Assets facts available at or before decision_at, with both asset observations eligible at that time.",
    ),
    FeatureDefinition(
        key="trailing_volatility_60d",
        version="v1",
        family="risk",
        direction="lower_is_better",
        display_name="60 day trailing volatility",
        description="Annualized standard deviation of recent split-adjusted daily log returns.",
        formula="stdev(log(C(t) / C(t-1)), 60 sessions) × sqrt(252).",
        required_inputs=("daily_price_bars:split_adjusted",),
        as_of_rule="Use 60 completed sessions whose bars were available at or before decision_at; t is the formation session.",
    ),
    FeatureDefinition(
        key="median_dollar_volume_20d",
        version="v1",
        family="liquidity",
        direction="higher_is_better",
        display_name="20 day median dollar volume",
        description="Median daily notional traded over the recent completed sessions.",
        formula="median(close × volume, 20 sessions), using unadjusted regular-session bars.",
        required_inputs=("daily_price_bars:unadjusted",),
        as_of_rule="Use 20 completed sessions whose bars were available at or before decision_at; t is the formation session.",
    ),
)


NEXT_GENERATION_CANDIDATE_SET_VERSION = "next_gen_free_v1"

NEXT_GENERATION_CANDIDATE_DEFINITIONS: tuple[FeatureDefinition, ...] = (
    FeatureDefinition(
        key="short_term_reversal_20d",
        version="v1",
        family="momentum",
        direction="lower_is_better",
        display_name="20 day short-term reversal",
        description="Recent split-adjusted return used to test whether short-term moves reverse.",
        formula="C(t) / C(t-20) - 1, using split-adjusted closes.",
        required_inputs=("daily_price_bars:split_adjusted",),
        as_of_rule="Use 21 completed regular sessions available at or before decision_at; t is the formation session.",
    ),
    FeatureDefinition(
        key="downside_volatility_60d",
        version="v1",
        family="risk",
        direction="lower_is_better",
        display_name="60 day downside volatility",
        description="Annualized downside deviation of recent split-adjusted daily log returns.",
        formula="sqrt(mean(min(log(C(t) / C(t-1)), 0)^2, 60 sessions) x 252).",
        required_inputs=("daily_price_bars:split_adjusted",),
        as_of_rule="Use 61 completed regular sessions available at or before decision_at; t is the formation session.",
    ),
    FeatureDefinition(
        key="amihud_illiquidity_20d",
        version="v1",
        family="liquidity",
        direction="lower_is_better",
        display_name="20 day Amihud illiquidity",
        description="Average absolute split-adjusted return per dollar of unadjusted trading volume.",
        formula="mean(abs(C_adj(t) / C_adj(t-1) - 1) / (C_raw(t) x volume(t)), 20 sessions).",
        required_inputs=("daily_price_bars:split_adjusted", "daily_price_bars:unadjusted"),
        as_of_rule="Use 20 matching completed return and dollar-volume sessions available at or before decision_at; reject zero dollar volume.",
    ),
    FeatureDefinition(
        key="return_on_assets_change_yoy",
        version="v1",
        family="profitability",
        direction="higher_is_better",
        display_name="Year-over-year return on assets change",
        description="Change in reported annual return on assets between the two latest eligible fiscal years.",
        formula="ROA(latest eligible annual filing) - ROA(previous eligible annual filing).",
        required_inputs=("filing_facts:us-gaap:NetIncomeLoss|ProfitLoss", "filing_facts:us-gaap:Assets"),
        as_of_rule="Use two distinct annual periods and their balance-sheet endpoints only when every selected SEC fact was public by decision_at.",
    ),
)


def baseline_feature_registry() -> FeatureRegistry:
    """Create the approved v1 feature registry without calculating features."""
    return FeatureRegistry(BASELINE_FEATURE_DEFINITIONS)


def next_generation_candidate_registry() -> FeatureRegistry:
    """Create the isolated free-data candidate registry used by Phase 9 research."""
    return FeatureRegistry(NEXT_GENERATION_CANDIDATE_DEFINITIONS)
