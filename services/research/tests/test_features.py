import unittest

from quantrade_research.features import (
    BASELINE_FEATURE_DEFINITIONS,
    FeatureDefinition,
    FeatureRegistry,
    FeatureRegistryError,
    baseline_feature_registry,
)


class FeatureDefinitionTests(unittest.TestCase):
    def test_definition_hash_is_deterministic(self) -> None:
        definition = BASELINE_FEATURE_DEFINITIONS[0]
        same_definition = FeatureDefinition(**definition.canonical_payload())
        self.assertEqual(definition.definition_hash, same_definition.definition_hash)
        self.assertEqual(len(definition.definition_hash), 64)

    def test_definition_requires_safe_identity_and_inputs(self) -> None:
        with self.assertRaisesRegex(FeatureRegistryError, "snake_case"):
            FeatureDefinition(
                key="Momentum-12-1",
                version="v1",
                family="momentum",
                direction="higher_is_better",
                display_name="Name",
                description="Description",
                formula="Formula",
                required_inputs=("daily_price_bars:split_adjusted",),
                as_of_rule="As of rule",
            )
        with self.assertRaisesRegex(FeatureRegistryError, "duplicates"):
            FeatureDefinition(
                key="momentum_12_1",
                version="v1",
                family="momentum",
                direction="higher_is_better",
                display_name="Name",
                description="Description",
                formula="Formula",
                required_inputs=("x", "x"),
                as_of_rule="As of rule",
            )

    def test_registry_prevents_replacement_and_hash_is_order_independent(self) -> None:
        first, second = BASELINE_FEATURE_DEFINITIONS[:2]
        forward = FeatureRegistry((first, second))
        reverse = FeatureRegistry((second, first))
        self.assertEqual(forward.registry_hash, reverse.registry_hash)
        with self.assertRaisesRegex(FeatureRegistryError, "already registered"):
            forward.register(first)

    def test_baseline_registry_covers_each_initial_family(self) -> None:
        registry = baseline_feature_registry()
        self.assertEqual(len(registry.definitions()), 6)
        self.assertEqual(
            {definition.family for definition in registry.definitions()},
            {"momentum", "value", "profitability", "risk", "liquidity"},
        )


if __name__ == "__main__":
    unittest.main()
