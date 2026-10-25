import unittest
from pathlib import Path

from streamlit.testing.v1 import AppTest


ROOT = Path(__file__).resolve().parents[1]


class DashboardSmokeTests(unittest.TestCase):
    def test_default_dataset_and_model_results_render(self):
        app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=180).run()
        self.assertFalse(app.exception, "The dashboard raised an exception.")
        self.assertEqual(app.title[0].value, "Lagos building footprint explorer")
        metrics = {item.label: item.value for item in app.metric}
        self.assertEqual(metrics["Predictions shown"], "53,437")
        self.assertEqual(metrics["Validation IoU"], "0.516")
        self.assertEqual(metrics["Test IoU"], "0.597")
        self.assertEqual(metrics["Test F1"], "0.748")
        self.assertTrue(
            any("Showing 17,813 of 53,437 footprint locations" in node.value for node in app.caption),
            "The map should include sampled points from the full 53,437-feature export.",
        )
        self.assertEqual([tab.label for tab in app.tabs], [
            "Overview", "Explore footprints", "Technical QA", "Guide & limits"
        ])


if __name__ == "__main__":
    unittest.main()
