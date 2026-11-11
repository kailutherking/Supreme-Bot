import json
import stat
import tempfile
import unittest
from pathlib import Path

from supremebot import TargetItem, load_config, matches_target


class LoadConfigTests(unittest.TestCase):
    def test_missing_file_creates_restricted_safe_defaults(self):
        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory) / "nested" / "config.json"

            config = load_config(config_path)

            self.assertEqual(config.target_items, ())
            self.assertFalse(config.headless)
            self.assertEqual(
                json.loads(config_path.read_text(encoding="utf-8")),
                {"target_items": [], "settings": {"headless": False}},
            )
            self.assertEqual(stat.S_IMODE(config_path.stat().st_mode) & 0o077, 0)

    def test_rejects_legacy_payment_and_checkout_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory) / "config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "target_items": [],
                        "billing_info": {"card_number": "example"},
                        "settings": {"auto_checkout": True},
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "billing_info"):
                load_config(config_path)

    def test_rejects_invalid_target_values(self):
        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory) / "config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "target_items": [{"keywords": [], "color": "Red"}],
                        "settings": {"headless": False},
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "keywords"):
                load_config(config_path)

    def test_reports_malformed_json(self):
        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory) / "config.json"
            config_path.write_text("{", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "Invalid JSON"):
                load_config(config_path)


class MatchTargetTests(unittest.TestCase):
    def test_matches_all_keywords_and_color_case_insensitively(self):
        target = TargetItem(keywords=("Faux", "Jacket"), color="Red")

        self.assertTrue(matches_target("Faux Fur Jacket", "Bright Red", target))
        self.assertFalse(matches_target("Faux Fur Coat", "Bright Red", target))
        self.assertFalse(matches_target("Faux Fur Jacket", "Blue", target))


if __name__ == "__main__":
    unittest.main()
