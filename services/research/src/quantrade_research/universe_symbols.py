"""Choose a stable, common-share ticker for a company-level research universe."""

from __future__ import annotations

import re
from collections.abc import Iterable


_SIMPLE_COMMON_TICKER = re.compile(r"^[A-Z]{1,5}$")
_CLASS_B_TICKER = re.compile(r"^[A-Z]+-B$")


def canonical_ticker(tickers: Iterable[str]) -> str:
    """Prefer a conventional common ticker and avoid preferred/warrant listings.

    The Tier-B universe is company/CIK based. SEC can list several active
    instruments under one CIK, so using every listing would overstate the
    universe and can overwrite one company's daily bar with another instrument.
    """
    candidates = sorted({ticker.strip().upper() for ticker in tickers if ticker.strip()})
    if not candidates:
        raise ValueError("a universe member has no active ticker candidates")
    return min(
        candidates,
        key=lambda ticker: (
            0 if _SIMPLE_COMMON_TICKER.fullmatch(ticker) else 1,
            0 if _CLASS_B_TICKER.fullmatch(ticker) else 1,
            len(ticker),
            ticker,
        ),
    )
