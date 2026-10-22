import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "results" / "lagos"))

from analyze_export import check_ring, confidence_distribution


class ConfidenceDistributionTests(unittest.TestCase):
    def test_default_cutoff_bins_partition_values(self):
        values = [0.75, 0.7999, 0.80, 0.85, 0.95, 1.0]
        bins = confidence_distribution(values, 0.75)
        self.assertEqual(sum(bins.values()), len(values))
        self.assertEqual(bins["0.75–0.80"], 2)
        self.assertEqual(bins["0.80–0.85"], 1)
        self.assertEqual(bins["0.85–0.90"], 1)
        self.assertEqual(bins["0.95–1.00"], 2)

    def test_non_aligned_cutoff_starts_at_actual_threshold(self):
        bins = confidence_distribution([0.83, 0.849, 0.85, 0.99], 0.83)
        self.assertEqual(list(bins)[0], "0.83–0.85")
        self.assertEqual(list(bins)[1], "0.85–0.90")
        self.assertEqual(sum(bins.values()), 4)

    def test_one_point_cutoff_has_clear_label(self):
        self.assertEqual(confidence_distribution([1.0], 1.0), {"1.00": 1})

    def test_rejects_cutoff_outside_unit_interval(self):
        with self.assertRaises(ValueError):
            confidence_distribution([0.5], 1.01)


class GeometryRingTests(unittest.TestCase):
    def test_closed_wgs84_ring_is_valid(self):
        valid, count, *_ = check_ring([[3, 6], [4, 6], [4, 7], [3, 6]])
        self.assertTrue(valid)
        self.assertEqual(count, 4)

    def test_open_ring_is_invalid(self):
        valid, *_ = check_ring([[3, 6], [4, 6], [4, 7], [3, 7]])
        self.assertFalse(valid)

    def test_out_of_range_coordinate_is_invalid(self):
        valid, *_ = check_ring([[181, 6], [4, 6], [4, 7], [181, 6]])
        self.assertFalse(valid)


if __name__ == "__main__":
    unittest.main()
