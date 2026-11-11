import json
import os
import stat
import tempfile
import unittest
from pathlib import Path

from src.shared.models import ProductFilter, ProductObservation
from supremebot import load_config, main


class LoadConfigTests(unittest.TestCase):
    def test_missing_file_creates_restricted_safe_defaults(self):
        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory) / "nested" / "config.json"

            config = load_config(config_path)

            self.assertEqual(config.filters, ())
            self.assertFalse(config.headless)
            self.assertEqual(
                config.database_path, Path("data/retail-monitor.sqlite3")
            )
            self.assertEqual(
                json.loads(config_path.read_text(encoding="utf-8")),
                {
                    "target_items": [],
                    "settings": {
                        "headless": False,
                        "database_path": "data/retail-monitor.sqlite3",
                    },
                },
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
        target = ProductFilter(keywords=("Faux", "Jacket"), color="Red")
        product = ProductObservation(
            site_id="example",
            product_id="sku-1",
            title="Faux Fur Jacket",
            color="Bright Red",
            url="https://shop.example/products/sku-1",
        )

        self.assertTrue(target.matches(product))
        self.assertFalse(
            target.matches(
                ProductObservation(
                    site_id="example",
                    product_id="sku-2",
                    title="Faux Fur Coat",
                    color="Bright Red",
                    url="https://shop.example/products/sku-2",
                )
            )
        )
        self.assertFalse(
            target.matches(
                ProductObservation(
                    site_id="example",
                    product_id="sku-3",
                    title="Faux Fur Jacket",
                    color="Blue",
                    url="https://shop.example/products/sku-3",
                )
            )
        )


class CliTests(unittest.TestCase):
    def test_first_run_writes_config_without_starting_browser(self):
        original_directory = Path.cwd()
        with tempfile.TemporaryDirectory() as directory:
            try:
                os.chdir(directory)
                self.assertEqual(main(), 0)
                self.assertTrue(Path("config.json").exists())
                self.assertFalse(Path("data/retail-monitor.sqlite3").exists())
            finally:
                os.chdir(original_directory)


if __name__ == "__main__":
    unittest.main()
