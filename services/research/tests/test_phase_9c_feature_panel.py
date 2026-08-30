from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
import sys
import unittest


SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

from quantrade_research.phase_9c_feature_panel import (
    AccountingSnapshot, CorporateAction, _accounting_feature_cells, _fieldnames,
)
from quantrade_research.phase_9c_features import PriceBar
from quantrade_research.quarterly_accounting import AccountingValue


UTC = timezone.utc


def value(amount: str, end: date, concept: str, *, start: date | None = None, unit: str = "USD"):
    return AccountingValue(
        Decimal(amount), unit, start or end, end, concept, "test", (),
    )


class Phase9CFeaturePanelTests(unittest.TestCase):
    def test_accounting_cells_use_unadjusted_market_cap_and_split_reconciled_issuance(self) -> None:
        formation = date(2025, 3, 31)
        snapshot = AccountingSnapshot(
            value("20", date(2024, 12, 31), "NetIncomeLoss", start=date(2024, 1, 1)),
            value("30", date(2024, 12, 31), "NetCashProvidedByUsedInOperatingActivities", start=date(2024, 1, 1)),
            value("110", date(2024, 12, 31), "Assets"),
            value("90", date(2023, 12, 31), "Assets"),
            value("55", date(2024, 12, 31), "StockholdersEquity"),
            value("220", date(2024, 12, 31), "EntityCommonStockSharesOutstanding", unit="shares"),
            value("100", date(2023, 12, 31), "EntityCommonStockSharesOutstanding", unit="shares"),
        )
        close = PriceBar(
            "bar", "security", formation, Decimal("10"),
            datetime(2025, 3, 31, 22, tzinfo=UTC), "unadjusted",
        )
        split = CorporateAction(
            "split", "security", "forward_split", date(2024, 6, 1), date(2024, 6, 1),
            Decimal("2"), Decimal("1"), datetime(2024, 6, 1, tzinfo=UTC), "source",
        )
        cells = _accounting_feature_cells(
            snapshot, formation=formation, raw_close=close, actions=(split,), catalog={},
        )
        self.assertEqual(cells["book_to_market"].value, Decimal("55") / Decimal("2200"))
        self.assertEqual(cells["net_share_issuance_yoy"].value, Decimal("0.1"))
        self.assertEqual(cells["accrual_quality_ttm"].value, Decimal("-0.1"))

    def test_structural_action_withholds_share_issuance(self) -> None:
        formation = date(2025, 3, 31)
        snapshot = AccountingSnapshot(
            value("20", date(2024, 12, 31), "NetIncomeLoss"),
            value("30", date(2024, 12, 31), "NetCashProvidedByUsedInOperatingActivities"),
            value("110", date(2024, 12, 31), "Assets"), value("90", date(2023, 12, 31), "Assets"),
            value("55", date(2024, 12, 31), "StockholdersEquity"),
            value("110", date(2024, 12, 31), "EntityCommonStockSharesOutstanding", unit="shares"),
            value("100", date(2023, 12, 31), "EntityCommonStockSharesOutstanding", unit="shares"),
        )
        action = CorporateAction(
            "spin", "security", "spin_off", date(2024, 6, 1), date(2024, 6, 1),
            None, None, datetime(2024, 6, 1, tzinfo=UTC), "source",
        )
        cell = _accounting_feature_cells(
            snapshot, formation=formation, raw_close=None, actions=(action,), catalog={},
        )["net_share_issuance_yoy"]
        self.assertFalse(cell.available)
        self.assertEqual(cell.exclusion, "structural_corporate_action")

    def test_compact_panel_does_not_repeat_per_feature_lineage_hashes(self) -> None:
        self.assertFalse(any(name.endswith("_lineage_hash") for name in _fieldnames()))
        self.assertIn("row_hash", _fieldnames())


if __name__ == "__main__":
    unittest.main()
