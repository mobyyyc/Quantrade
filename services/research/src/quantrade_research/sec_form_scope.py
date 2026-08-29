"""Canonical SEC form scope shared by ingestion and model inputs."""

from __future__ import annotations


MODEL_RELEVANT_FINANCIAL_FORMS = frozenset({"10-K", "10-Q", "20-F", "40-F"})
RESEARCH_RELEVANT_FORMS = MODEL_RELEVANT_FINANCIAL_FORMS | {"8-K"}


def canonical_form(value: str) -> str:
    """Normalize a submitted form while preserving only the approved base forms."""
    normalized = value.strip().upper().removesuffix("/A")
    return normalized if normalized in RESEARCH_RELEVANT_FORMS else "other"


def is_research_relevant_form(value: str) -> bool:
    """Return whether a submitted or canonical form is in the research scope."""
    return canonical_form(value) in RESEARCH_RELEVANT_FORMS
