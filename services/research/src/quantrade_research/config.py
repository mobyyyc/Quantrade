"""Local-only configuration and secret-safe operational metadata."""

from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
import json
import os
from typing import Literal, Mapping


Environment = Literal["development", "test", "production"]


class ConfigurationError(ValueError):
    """Raised when configuration is inconsistent or unsafe to use."""


def _optional_value(values: Mapping[str, str], key: str) -> str | None:
    value = values.get(key, "").strip()
    return value or None


@dataclass(frozen=True, slots=True)
class Settings:
    environment: Environment
    database_url: str | None = field(repr=False)
    raw_artifacts_uri: str | None
    sec_user_agent: str | None
    alpaca_key_id: str | None = field(repr=False)
    alpaca_secret_key: str | None = field(repr=False)
    fred_api_key: str | None = field(repr=False)

    @classmethod
    def from_environment(cls, values: Mapping[str, str] | None = None) -> "Settings":
        source = values if values is not None else os.environ
        environment = _optional_value(source, "QUANTRADE_ENVIRONMENT") or "development"
        if environment not in {"development", "test", "production"}:
            raise ConfigurationError("QUANTRADE_ENVIRONMENT must be development, test, or production")

        alpaca_key_id = _optional_value(source, "APCA_API_KEY_ID")
        alpaca_secret_key = _optional_value(source, "APCA_API_SECRET_KEY")
        if bool(alpaca_key_id) != bool(alpaca_secret_key):
            raise ConfigurationError(
                "APCA_API_KEY_ID and APCA_API_SECRET_KEY must be set together"
            )

        settings = cls(
            environment=environment,
            database_url=_optional_value(source, "DATABASE_URL"),
            raw_artifacts_uri=_optional_value(source, "RAW_ARTIFACTS_URI"),
            sec_user_agent=_optional_value(source, "SEC_USER_AGENT"),
            alpaca_key_id=alpaca_key_id,
            alpaca_secret_key=alpaca_secret_key,
            fred_api_key=_optional_value(source, "FRED_API_KEY"),
        )
        if settings.environment == "production":
            settings.require_runtime_storage()
        return settings

    def require_runtime_storage(self) -> None:
        if self.database_url is None:
            raise ConfigurationError("DATABASE_URL is required for database-backed runs")
        if self.raw_artifacts_uri is None:
            raise ConfigurationError("RAW_ARTIFACTS_URI is required for reproducible runs")

    def redacted_summary(self) -> dict[str, object]:
        """Return operational state without values that could contain secrets."""
        return {
            "environment": self.environment,
            "databaseConfigured": self.database_url is not None,
            "rawArtifactsConfigured": self.raw_artifacts_uri is not None,
            "secUserAgentConfigured": self.sec_user_agent is not None,
            "alpacaCredentialsConfigured": self.alpaca_key_id is not None,
            "fredCredentialsConfigured": self.fred_api_key is not None,
        }

    def configuration_fingerprint(self) -> str:
        canonical = json.dumps(
            self.redacted_summary(), separators=(",", ":"), sort_keys=True
        )
        return sha256(canonical.encode("utf-8")).hexdigest()
