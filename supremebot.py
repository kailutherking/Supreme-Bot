"""CLI entry point for the read-only retail monitor."""

from __future__ import annotations

import json
import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.core.monitor_engine import MonitorEngine
from src.core.notifications import NotificationError, notifiers_from_environment
from src.core.site_registry import SiteRegistry
from src.core.storage import SQLiteStorage
from src.shared.models import MonitorQuery, ProductFilter
from src.sites.supreme.adapter import SiteDependencyError, SiteTimeoutError, SupremeSite


CONFIG_DEFAULTS = {
    "target_items": [],
    "settings": {
        "headless": False,
        "database_path": "data/retail-monitor.sqlite3",
    },
}


@dataclass(frozen=True)
class AppConfig:
    filters: tuple[ProductFilter, ...]
    headless: bool
    database_path: Path


def _write_default_config(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return

    with os.fdopen(descriptor, "w", encoding="utf-8") as config_file:
        json.dump(CONFIG_DEFAULTS, config_file, indent=2)
        config_file.write("\n")


def load_config(config_path: str | Path) -> AppConfig:
    path = Path(config_path)
    try:
        with path.open(encoding="utf-8") as config_file:
            data: Any = json.load(config_file)
    except FileNotFoundError:
        _write_default_config(path)
        try:
            with path.open(encoding="utf-8") as config_file:
                data = json.load(config_file)
        except json.JSONDecodeError as error:
            raise ValueError(f"Invalid generated configuration: {error}") from error
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

    filters: list[ProductFilter] = []
    for index, target in enumerate(targets_data):
        if not isinstance(target, dict):
            raise ValueError(f"target_items[{index}] must be an object.")
        unexpected_fields = set(target) - {"keywords", "color"}
        if unexpected_fields:
            raise ValueError(
                f"target_items[{index}] has unsupported field(s): "
                f"{', '.join(sorted(unexpected_fields))}."
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
        filters.append(
            ProductFilter(
                keywords=tuple(word.strip() for word in keywords),
                color=color.strip(),
            )
        )

    settings = data.get("settings")
    if not isinstance(settings, dict):
        raise ValueError("'settings' must be an object.")
    unexpected_settings = set(settings) - {"headless", "database_path"}
    if unexpected_settings:
        raise ValueError(
            "Unsupported setting(s): "
            f"{', '.join(sorted(unexpected_settings))}."
        )

    headless = settings.get("headless", False)
    if not isinstance(headless, bool):
        raise ValueError("'settings.headless' must be true or false.")
    database_path = settings.get("database_path", CONFIG_DEFAULTS["settings"]["database_path"])
    if not isinstance(database_path, str) or not database_path.strip():
        raise ValueError("'settings.database_path' must be a non-empty path.")

    return AppConfig(
        filters=tuple(filters),
        headless=headless,
        database_path=Path(database_path),
    )


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    logger = logging.getLogger("retail-monitor")
    config_path = Path("config.json")
    config_existed = config_path.exists()
    try:
        config = load_config(config_path)
    except (OSError, ValueError) as error:
        logger.error("%s", error)
        return 2

    if not config_existed:
        logger.info(
            "Created %s with safe defaults; add target_items before scanning.",
            config_path,
        )
        return 0
    if not config.filters:
        logger.error("No target_items configured. Edit config.json and run again.")
        return 2

    try:
        notifications = notifiers_from_environment()
    except ValueError as error:
        logger.error("%s", error)
        return 2

    registry = SiteRegistry()
    registry.register(SupremeSite(headless=config.headless))
    engine = MonitorEngine(
        registry,
        SQLiteStorage(config.database_path),
        notifications=notifications,
    )

    try:
        summary = engine.scan_once(MonitorQuery(filters=config.filters))
    except SiteTimeoutError as error:
        logger.error("%s", error)
        return 1
    except SiteDependencyError as error:
        logger.error("%s", error)
        return 2
    except NotificationError as error:
        logger.error("Notification delivery failed; events remain queued: %s", error)
        return 1

    logger.info(
        "Scan complete: %d site(s), %d product observation(s), %d new event(s), "
        "%d event notification(s) delivered.",
        summary.sites_scanned,
        summary.products_observed,
        summary.events_created,
        summary.notifications_delivered,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
