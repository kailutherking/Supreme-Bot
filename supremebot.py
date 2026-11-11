"""One-shot, read-only Supreme product-listing monitor."""

from __future__ import annotations

import json
import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


BASE_URL = "https://www.supremenewyork.com"
SHOP_PATH = "/shop/all/jackets"
CONFIG_DEFAULTS = {
    "target_items": [],
    "settings": {"headless": False},
}


@dataclass(frozen=True)
class TargetItem:
    keywords: tuple[str, ...]
    color: str


@dataclass(frozen=True)
class MonitorConfig:
    target_items: tuple[TargetItem, ...]
    headless: bool


class MissingDependencyError(RuntimeError):
    pass


def _write_default_config(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return

    with os.fdopen(descriptor, "w", encoding="utf-8") as config_file:
        json.dump(CONFIG_DEFAULTS, config_file, indent=2)
        config_file.write("\n")


def load_config(config_path: str | Path) -> MonitorConfig:
    path = Path(config_path)
    try:
        with path.open(encoding="utf-8") as config_file:
            data: Any = json.load(config_file)
    except FileNotFoundError:
        _write_default_config(path)
        with path.open(encoding="utf-8") as config_file:
            data = json.load(config_file)
    except json.JSONDecodeError as error:
        raise ValueError(f"Invalid JSON in {path}: {error}") from error

    if not isinstance(data, dict):
        raise ValueError("Configuration must be a JSON object.")

    unexpected = set(data) - {"target_items", "settings"}
    if unexpected:
        raise ValueError(
            "Unsupported configuration field(s): "
            f"{', '.join(sorted(unexpected))}. This monitor does not accept "
            "billing details, credentials, or checkout settings."
        )

    targets_data = data.get("target_items")
    if not isinstance(targets_data, list):
        raise ValueError("'target_items' must be a list.")

    targets: list[TargetItem] = []
    for index, target in enumerate(targets_data):
        if not isinstance(target, dict):
            raise ValueError(f"target_items[{index}] must be an object.")
        unexpected_target_fields = set(target) - {"keywords", "color"}
        if unexpected_target_fields:
            raise ValueError(
                f"target_items[{index}] has unsupported field(s): "
                f"{', '.join(sorted(unexpected_target_fields))}."
            )

        keywords = target.get("keywords")
        color = target.get("color")
        if (
            not isinstance(keywords, list)
            or not keywords
            or any(not isinstance(word, str) or not word.strip() for word in keywords)
        ):
            raise ValueError(
                f"target_items[{index}].keywords must be a non-empty list of strings."
            )
        if not isinstance(color, str) or not color.strip():
            raise ValueError(f"target_items[{index}].color must be a non-empty string.")

        targets.append(
            TargetItem(
                keywords=tuple(word.strip() for word in keywords),
                color=color.strip(),
            )
        )

    settings = data.get("settings")
    if not isinstance(settings, dict):
        raise ValueError("'settings' must be an object.")
    unexpected_settings = set(settings) - {"headless"}
    if unexpected_settings:
        raise ValueError(
            "Unsupported setting(s): "
            f"{', '.join(sorted(unexpected_settings))}. Only 'headless' is supported."
        )
    headless = settings.get("headless", False)
    if not isinstance(headless, bool):
        raise ValueError("'settings.headless' must be true or false.")

    return MonitorConfig(target_items=tuple(targets), headless=headless)


def matches_target(name: str, color: str, target: TargetItem) -> bool:
    normalized_name = name.casefold()
    normalized_color = color.casefold()
    return all(word.casefold() in normalized_name for word in target.keywords) and (
        target.color.casefold() in normalized_color
    )


class SupremeMonitor:
    def __init__(self, config: MonitorConfig) -> None:
        self.config = config
        self.logger = logging.getLogger("supreme-monitor")

    def _create_driver(self, webdriver: Any, options_type: Any) -> Any:
        options = options_type()
        if self.config.headless:
            options.add_argument("--headless=new")
        driver = webdriver.Chrome(options=options)
        driver.set_page_load_timeout(30)
        return driver

    def run(self) -> int:
        if not self.config.target_items:
            self.logger.error(
                "No target_items configured. Edit config.json and run again."
            )
            return 2

        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            from selenium.common.exceptions import (
                NoSuchElementException,
                TimeoutException,
            )
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support import expected_conditions as expected
            from selenium.webdriver.support.ui import WebDriverWait
        except ModuleNotFoundError as error:
            raise MissingDependencyError(
                "Selenium is required. Install project dependencies with "
                "'python -m pip install -r requirements.txt'."
            ) from error

        driver = None
        try:
            driver = self._create_driver(webdriver, Options)
            try:
                driver.get(BASE_URL + SHOP_PATH)
                WebDriverWait(driver, 20).until(
                    expected.presence_of_element_located(
                        (By.CLASS_NAME, "inner-article")
                    )
                )
            except TimeoutException:
                self.logger.warning("The shop page or listings timed out.")
                return 1

            cards = driver.find_elements(By.CLASS_NAME, "inner-article")
            matches = 0
            for card in cards:
                try:
                    name = card.find_element(By.CLASS_NAME, "name").text.strip()
                    color = card.find_element(By.CLASS_NAME, "style").text.strip()
                    link = card.find_element(By.TAG_NAME, "a").get_attribute("href")
                except NoSuchElementException:
                    self.logger.debug("Skipping a listing with missing fields.")
                    continue

                if not link:
                    continue
                for target in self.config.target_items:
                    if matches_target(name, color, target):
                        matches += 1
                        self.logger.info(
                            "Match: %s (%s) — open the listing to verify availability "
                            "and variant: %s",
                            name,
                            color,
                            link,
                        )

            if matches == 0:
                self.logger.info("No configured product listings matched.")
            return 0
        finally:
            if driver is not None:
                driver.quit()


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    config_path = Path("config.json")
    config_existed = config_path.exists()
    try:
        config = load_config(config_path)
    except (OSError, ValueError) as error:
        logging.getLogger("supreme-monitor").error("%s", error)
        return 2

    if not config_existed:
        logging.getLogger("supreme-monitor").info(
            "Created %s with safe defaults; add targets before running.", config_path
        )
        return 0

    try:
        return SupremeMonitor(config).run()
    except MissingDependencyError as error:
        logging.getLogger("supreme-monitor").error("%s", error)
        return 2


if __name__ == "__main__":
    sys.exit(main())
