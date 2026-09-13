import unittest

from quantrade_research.active_model import ActiveModelArtifact
from quantrade_research.features import baseline_feature_registry
from quantrade_research.model_input_contract import build_model_input_contracts


class ModelInputContractTests(unittest.TestCase):
    def test_contract_preserves_artifact_order_and_exact_zero_status(self) -> None:
        registry = baseline_feature_registry()
        columns = tuple(f"{item.key}_percentile" for item in registry.definitions())
        coefficients = (0.1, 0.0, -0.0, -0.2, 0.3, 0.0)
        model = ActiveModelArtifact(
            "model-v1", "protocol-v1", registry.registry_hash, columns,
            tuple(0.0 for _ in columns), tuple(1.0 for _ in columns), 0.0,
            coefficients,
        )

        contracts = build_model_input_contracts(model, registry)

        self.assertEqual(tuple(item.input_ordinal for item in contracts), tuple(range(1, 7)))
        self.assertEqual(tuple(item.model_column for item in contracts), columns)
        self.assertEqual(
            tuple(item.is_active for item in contracts),
            (True, False, False, True, True, False),
        )
        self.assertTrue(all(item.display_name for item in contracts))


if __name__ == "__main__":
    unittest.main()
