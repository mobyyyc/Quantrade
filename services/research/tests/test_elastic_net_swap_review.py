from dataclasses import replace
from datetime import date
import unittest
from unittest.mock import patch

from quantrade_research.elastic_net_swap_review import compare
from quantrade_research.monthly_model_comparison import Example
from quantrade_research.quality import DataQualityError


class SwapReviewTests(unittest.TestCase):
    def rows(self):
        return [Example(date(year, month, 1), date(year, month, 28), str(i),
                        tuple((i + j) / 30 for j in range(6)), (), (),
                        i / 100, i / 100, 0, 1 / 30, 0, 0)
                for year in (2022, 2023) for month in range(1, 7) for i in range(30)]

    def test_identical_recipes_match_without_deployment(self):
        with patch("quantrade_research.elastic_net_swap_review.OUTER_BLOCKS",
                   ((date(2023, 1, 1), date(2023, 6, 30)),)):
            result = compare(self.rows(), {"current": (.001, .001), "new": (.001, .001)})
        self.assertEqual(result["results"]["current"], result["results"]["new"])
        self.assertTrue(all(x == 0 for x in result["top20_names_different_by_formation"].values()))
        self.assertFalse(result["deployed"])
        self.assertFalse(result["holdout_read"])

    def test_holdout_rejected(self):
        rows = self.rows()
        rows[0] = replace(rows[0], outcome_date=date(2025, 7, 1))
        with self.assertRaisesRegex(DataQualityError, "holdout"):
            compare(rows, {})

    def test_duplicate_rejected(self):
        rows = self.rows()
        with self.assertRaisesRegex(DataQualityError, "duplicate"):
            compare([*rows, rows[0]], {})
