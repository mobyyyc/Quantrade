"""Immutable model-card and rejected-hypothesis governance records."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from .quality import DataQualityError


ModelCardStatus = Literal["research_only", "private_beta_approved", "rejected"]


@dataclass(frozen=True, slots=True)
class ModelCard:
    model_version: str
    status: ModelCardStatus
    protocol_version: str
    feature_registry_hash: str
    data_capability_tier: str
    created_at: datetime
    purpose: str
    methodology: str
    limitations: tuple[str, ...]
    evaluation_uri: str | None = None

    def __post_init__(self) -> None:
        if not all((self.model_version.strip(), self.protocol_version.strip(), self.purpose.strip(), self.methodology.strip())):
            raise DataQualityError("model card identity, protocol, purpose, and methodology are required")
        if self.status not in ("research_only", "private_beta_approved", "rejected"):
            raise DataQualityError("unsupported model card status")
        if len(self.feature_registry_hash) != 64 or self.data_capability_tier not in ("A", "B", "C"):
            raise DataQualityError("model card requires a SHA-256 registry hash and valid data tier")
        if not self.limitations or any(not limitation.strip() for limitation in self.limitations):
            raise DataQualityError("model card requires at least one limitation")
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise DataQualityError("model card timestamp must include a UTC offset")


@dataclass(frozen=True, slots=True)
class RejectedHypothesisRecord:
    hypothesis_key: str
    recorded_at: datetime
    statement: str
    rejection_reason: str
    evidence_uri: str | None = None

    def __post_init__(self) -> None:
        if not all((self.hypothesis_key.strip(), self.statement.strip(), self.rejection_reason.strip())):
            raise DataQualityError("rejected hypothesis key, statement, and reason are required")
        if self.recorded_at.tzinfo is None or self.recorded_at.utcoffset() is None:
            raise DataQualityError("rejected hypothesis timestamp must include a UTC offset")


class GovernanceRegistry:
    """Append-only in-memory representation of immutable governance records."""

    def __init__(self) -> None:
        self._model_cards: dict[str, ModelCard] = {}
        self._rejected_hypotheses: dict[str, RejectedHypothesisRecord] = {}

    def add_model_card(self, card: ModelCard) -> None:
        if card.model_version in self._model_cards:
            raise DataQualityError(f"model card already recorded: {card.model_version}")
        self._model_cards[card.model_version] = card

    def reject_hypothesis(self, record: RejectedHypothesisRecord) -> None:
        if record.hypothesis_key in self._rejected_hypotheses:
            raise DataQualityError(f"rejected hypothesis already recorded: {record.hypothesis_key}")
        self._rejected_hypotheses[record.hypothesis_key] = record

    def model_cards(self) -> tuple[ModelCard, ...]:
        return tuple(sorted(self._model_cards.values(), key=lambda card: (card.created_at, card.model_version)))

    def rejected_hypotheses(self) -> tuple[RejectedHypothesisRecord, ...]:
        return tuple(sorted(self._rejected_hypotheses.values(), key=lambda record: (record.recorded_at, record.hypothesis_key)))
