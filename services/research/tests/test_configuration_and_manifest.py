from datetime import datetime, timezone
from pathlib import Path
import sys
import tempfile
import unittest


SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

from quantrade_research.config import ConfigurationError, Settings
from quantrade_research.run_manifest import RunManifest, SourceInput


class SettingsTests(unittest.TestCase):
    def test_market_provider_defaults_to_alpaca_and_is_not_secret(self) -> None:
        self.assertEqual(Settings.from_environment({}).market_data_provider, "alpaca")
        settings = Settings.from_environment({"MARKET_DATA_PROVIDER": "ALTERNATE"})
        self.assertEqual(settings.market_data_provider, "alternate")
        self.assertEqual(settings.redacted_summary()["marketDataProvider"], "alternate")

    def test_alpaca_credentials_must_be_paired(self) -> None:
        with self.assertRaises(ConfigurationError):
            Settings.from_environment({"APCA_API_KEY_ID": "only-one-half"})

    def test_redacted_summary_never_contains_secret_values(self) -> None:
        settings = Settings.from_environment(
            {
                "DATABASE_URL": "postgresql://user:secret@localhost/quantrade",
                "APCA_API_KEY_ID": "key-value",
                "APCA_API_SECRET_KEY": "secret-value",
                "FRED_API_KEY": "fred-secret",
            }
        )
        summary = str(settings.redacted_summary())
        self.assertNotIn("secret-value", summary)
        self.assertNotIn("fred-secret", summary)
        self.assertNotIn("postgresql://", summary)


class RunManifestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.settings = Settings.from_environment({"QUANTRADE_ENVIRONMENT": "test"})
        self.source = SourceInput(
            provider="sec_edgar",
            source_reference="CIK0000320193",
            raw_artifact_uris=("file:///artifacts/aapl.json",),
        )

    def test_score_manifest_is_dated_and_secret_safe(self) -> None:
        manifest = RunManifest.create(
            settings=self.settings,
            run_kind="score",
            code_revision="a" * 40,
            data_capability_tier="B",
            source_inputs=(self.source,),
            decision_at=datetime(2026, 8, 20, 20, tzinfo=timezone.utc),
        )
        self.assertEqual(manifest.decision_at, "2026-08-20T20:00:00Z")
        self.assertEqual(manifest.configuration["environment"], "test")
        self.assertNotIn("api_key", manifest.to_json().lower())

    def test_manifest_write_is_canonical_json(self) -> None:
        manifest = RunManifest.create(
            settings=self.settings,
            run_kind="ingestion",
            code_revision="b" * 40,
            data_capability_tier="B",
            source_inputs=(self.source,),
        )
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            destination = Path(directory) / "run.json"
            manifest.write(destination)
            self.assertEqual(destination.read_text(encoding="utf-8"), manifest.to_json())


if __name__ == "__main__":
    unittest.main()
