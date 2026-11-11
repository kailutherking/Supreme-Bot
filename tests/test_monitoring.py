from datetime import datetime, timedelta, timezone
from decimal import Decimal
import sqlite3
import tempfile
import unittest
from pathlib import Path

from src.core.monitor_engine import MonitorEngine
from src.core.site_registry import SiteRegistry
from src.core.storage import SQLiteStorage
from src.shared.models import (
    EventType,
    MonitorQuery,
    ProductFilter,
    ProductObservation,
)


def product(
    *,
    available: bool | None = None,
    price: str | None = None,
    variant_id: str | None = None,
    observed_at: datetime | None = None,
    release_at: datetime | None = None,
) -> ProductObservation:
    return ProductObservation(
        site_id="sample",
        product_id="sku-1",
        variant_id=variant_id,
        title="Canvas Jacket",
        color="Olive",
        url="https://shop.example/products/sku-1",
        image_url="https://cdn.example/sku-1.jpg",
        price=Decimal(price) if price is not None else None,
        currency="USD" if price is not None else None,
        available=available,
        collection_id="outerwear",
        observed_at=observed_at or datetime.now(timezone.utc),
        release_at=release_at,
    )


class SQLiteStorageTests(unittest.TestCase):
    def test_records_history_and_detects_restock_and_price_change(self):
        with tempfile.TemporaryDirectory() as directory:
            storage = SQLiteStorage(Path(directory) / "monitor.sqlite3")
            storage.initialize()

            first_events = storage.record(
                product(
                    available=False,
                    price="100.00",
                    release_at=datetime(2026, 12, 1, tzinfo=timezone.utc),
                )
            )
            second_events = storage.record(
                product(
                    available=True,
                    price="110.00",
                    observed_at=datetime.now(timezone.utc) + timedelta(seconds=1),
                    release_at=datetime(2026, 12, 2, tzinfo=timezone.utc),
                )
            )

            self.assertEqual(
                [event.event_type for event in first_events],
                [EventType.PRODUCT_DISCOVERED],
            )
            self.assertEqual(
                {event.event_type for event in second_events},
                {
                    EventType.RESTOCKED,
                    EventType.PRICE_CHANGED,
                    EventType.RELEASE_CHANGED,
                },
            )
            self.assertEqual(len(storage.history("sample", "sku-1")), 2)
            self.assertEqual(
                storage.analytics(),
                {
                    "products": 1,
                    "observations": 2,
                    "restocks": 1,
                    "pending_notifications": 4,
                    "events_product_discovered": 1,
                    "events_price_changed": 1,
                    "events_restocked": 1,
                    "events_release_changed": 1,
                },
            )

    def test_variant_and_event_outbox(self):
        with tempfile.TemporaryDirectory() as directory:
            storage = SQLiteStorage(Path(directory) / "monitor.sqlite3")
            storage.initialize()
            storage.record(product(available=None))
            events = storage.record(product(variant_id="olive-m", available=None))

            self.assertEqual(events[0].event_type, EventType.VARIANT_DISCOVERED)
            pending = storage.pending_events()
            self.assertEqual(len(pending), 2)
            storage.mark_delivered(pending[0].event_id)
            self.assertEqual(len(storage.pending_events()), 1)

    def test_unknown_fields_do_not_erase_last_known_product_state(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "monitor.sqlite3"
            storage = SQLiteStorage(database)
            storage.initialize()
            storage.record(product(available=False, price="100.00"))

            events = storage.record(product(available=None, price=None))

            self.assertEqual(events, ())
            with sqlite3.connect(database) as connection:
                row = connection.execute(
                    """
                    SELECT price, available FROM products
                    WHERE site_id = ? AND product_id = ?
                    """,
                    ("sample", "sku-1"),
                ).fetchone()
            self.assertEqual(row, ("100.00", 0))


class MonitorEngineTests(unittest.TestCase):
    def test_registry_and_engine_filter_observations(self):
        class FakeSite:
            site_id = "sample"

            def discover(self, query):
                observations = (
                    product(),
                    ProductObservation(
                        site_id="sample",
                        product_id="sku-2",
                        title="Running Shoe",
                        url="https://shop.example/products/sku-2",
                    ),
                )
                return tuple(item for item in observations if query.matches(item))

        class FakeNotifications:
            def __init__(self):
                self.events = []

            def publish(self, event):
                self.events.append(event)

        with tempfile.TemporaryDirectory() as directory:
            registry = SiteRegistry()
            registry.register(FakeSite())
            with self.assertRaisesRegex(ValueError, "already registered"):
                registry.register(FakeSite())

            notifications = FakeNotifications()
            engine = MonitorEngine(
                registry,
                SQLiteStorage(Path(directory) / "monitor.sqlite3"),
                notifications=notifications,
            )
            summary = engine.scan_once(
                MonitorQuery(
                    filters=(ProductFilter(keywords=("jacket",), color="olive"),)
                )
            )

            self.assertEqual(summary.sites_scanned, 1)
            self.assertEqual(summary.products_observed, 1)
            self.assertEqual(summary.events_created, 1)
            self.assertEqual(summary.notifications_delivered, 1)
            self.assertEqual(len(notifications.events), 1)

    def test_failed_notification_remains_pending_for_retry(self):
        class FakeSite:
            site_id = "sample"

            def discover(self, query):
                item = product()
                return (item,) if query.matches(item) else ()

        class FailedNotifications:
            def publish(self, event):
                del event
                raise RuntimeError("transport unavailable")

        with tempfile.TemporaryDirectory() as directory:
            storage = SQLiteStorage(Path(directory) / "monitor.sqlite3")
            registry = SiteRegistry()
            registry.register(FakeSite())
            engine = MonitorEngine(
                registry,
                storage,
                notifications=FailedNotifications(),
            )
            with self.assertRaisesRegex(RuntimeError, "transport unavailable"):
                engine.scan_once(MonitorQuery())
            self.assertEqual(len(storage.pending_events()), 1)
