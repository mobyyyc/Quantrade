from datetime import datetime, timezone
import unittest

from quantrade_research.governance import GovernanceRegistry, ModelCard, RejectedHypothesisRecord
from quantrade_research.quality import DataQualityError


NOW = datetime(2026, 8, 20, 20, tzinfo=timezone.utc)


def card() -> ModelCard:
    return ModelCard(
        "baseline_equal_weight_v1", "research_only", "0.1", "a" * 64, "B", NOW,
        "Transparent reference", "Equal-weight ranks", ("Tier B data",),
    )


class GovernanceRecordTests(unittest.TestCase):
    def test_records_are_append_only(self) -> None:
        registry = GovernanceRegistry()
        registry.add_model_card(card())
        registry.reject_hypothesis(
            RejectedHypothesisRecord("same_close", NOW, "Same-close fill", "Look-ahead execution")
        )
        self.assertEqual(registry.model_cards(), (card(),))
        with self.assertRaisesRegex(DataQualityError, "already recorded"):
            registry.add_model_card(card())
        with self.assertRaisesRegex(DataQualityError, "already recorded"):
            registry.reject_hypothesis(
                RejectedHypothesisRecord("same_close", NOW, "Same-close fill", "Look-ahead execution")
            )

    def test_model_card_requires_limitations_and_valid_data_tier(self) -> None:
        with self.assertRaisesRegex(DataQualityError, "limitation"):
            ModelCard("model", "research_only", "0.1", "a" * 64, "B", NOW, "purpose", "method", ())
        with self.assertRaisesRegex(DataQualityError, "valid data tier"):
            ModelCard("model", "research_only", "0.1", "a" * 64, "Z", NOW, "purpose", "method", ("limit",))


if __name__ == "__main__":
    unittest.main()
