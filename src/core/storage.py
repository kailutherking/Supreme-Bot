from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Generator

from src.shared.models import EventType, ProductEvent, ProductObservation


_SCHEMA = """
CREATE TABLE IF NOT EXISTS products (
    site_id TEXT NOT NULL,
    product_id TEXT NOT NULL,
    variant_id TEXT NOT NULL DEFAULT '',
    title TEXT NOT NULL,
    url TEXT NOT NULL,
    color TEXT,
    image_url TEXT,
    price TEXT,
    currency TEXT,
    available INTEGER,
    collection_id TEXT,
    release_at TEXT,
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    PRIMARY KEY (site_id, product_id, variant_id)
);

CREATE TABLE IF NOT EXISTS observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    site_id TEXT NOT NULL,
    product_id TEXT NOT NULL,
    variant_id TEXT NOT NULL DEFAULT '',
    observed_at TEXT NOT NULL,
    payload TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS observations_product_time
    ON observations(site_id, product_id, variant_id, observed_at);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    site_id TEXT NOT NULL,
    product_id TEXT NOT NULL,
    variant_id TEXT NOT NULL DEFAULT '',
    occurred_at TEXT NOT NULL,
    previous_value TEXT,
    current_value TEXT,
    payload TEXT NOT NULL,
    delivered_at TEXT
);
CREATE INDEX IF NOT EXISTS events_pending
    ON events(delivered_at, occurred_at);
"""


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _observation_payload(product: ProductObservation) -> str:
    return json.dumps(
        {
            "site_id": product.site_id,
            "product_id": product.product_id,
            "variant_id": product.variant_id,
            "title": product.title,
            "url": product.url,
            "observed_at": product.observed_at.isoformat(),
            "color": product.color,
            "image_url": product.image_url,
            "price": str(product.price) if product.price is not None else None,
            "currency": product.currency,
            "available": product.available,
            "collection_id": product.collection_id,
            "release_at": _iso(product.release_at),
        },
        separators=(",", ":"),
    )


def _observation_from_payload(payload: str) -> ProductObservation:
    data = json.loads(payload)
    return ProductObservation(
        site_id=data["site_id"],
        product_id=data["product_id"],
        variant_id=data["variant_id"],
        title=data["title"],
        url=data["url"],
        observed_at=datetime.fromisoformat(data["observed_at"]),
        color=data["color"],
        image_url=data["image_url"],
        price=Decimal(data["price"]) if data["price"] is not None else None,
        currency=data["currency"],
        available=data["available"],
        collection_id=data["collection_id"],
        release_at=(
            datetime.fromisoformat(data["release_at"])
            if data["release_at"] is not None
            else None
        ),
    )


class SQLiteStorage:
    """Durable local product, observation, event, and notification-outbox store."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    @contextmanager
    def _connection(self) -> Generator[sqlite3.Connection, None, None]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=5)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA busy_timeout = 5000")
            yield connection
        finally:
            connection.close()

    def initialize(self) -> None:
        with self._connection() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.executescript(_SCHEMA)

    def record(self, product: ProductObservation) -> tuple[ProductEvent, ...]:
        variant_key = product.variant_id or ""
        observed_at = product.observed_at.isoformat()
        price = str(product.price) if product.price is not None else None
        available = (
            int(product.available) if product.available is not None else None
        )
        release_at = _iso(product.release_at)
        payload = _observation_payload(product)

        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            previous = connection.execute(
                """
                SELECT title, url, color, image_url, price, currency, available,
                       collection_id, release_at
                FROM products
                WHERE site_id = ? AND product_id = ? AND variant_id = ?
                """,
                (product.site_id, product.product_id, variant_key),
            ).fetchone()

            events = self._derive_events(
                connection, product, variant_key, previous, price, available, release_at
            )

            connection.execute(
                """
                INSERT INTO products (
                    site_id, product_id, variant_id, title, url, color, image_url,
                    price, currency, available, collection_id, release_at,
                    first_seen, last_seen
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(site_id, product_id, variant_id) DO UPDATE SET
                    title = excluded.title,
                    url = excluded.url,
                    color = COALESCE(excluded.color, products.color),
                    image_url = COALESCE(excluded.image_url, products.image_url),
                    price = COALESCE(excluded.price, products.price),
                    currency = COALESCE(excluded.currency, products.currency),
                    available = COALESCE(excluded.available, products.available),
                    collection_id = COALESCE(
                        excluded.collection_id, products.collection_id
                    ),
                    release_at = COALESCE(excluded.release_at, products.release_at),
                    last_seen = excluded.last_seen
                """,
                (
                    product.site_id,
                    product.product_id,
                    variant_key,
                    product.title,
                    product.url,
                    product.color,
                    product.image_url,
                    price,
                    product.currency,
                    available,
                    product.collection_id,
                    release_at,
                    observed_at,
                    observed_at,
                ),
            )
            connection.execute(
                """
                INSERT INTO observations (
                    site_id, product_id, variant_id, observed_at, payload
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    product.site_id,
                    product.product_id,
                    variant_key,
                    observed_at,
                    payload,
                ),
            )

            persisted_events: list[ProductEvent] = []
            for event_type, old_value, new_value in events:
                cursor = connection.execute(
                    """
                    INSERT INTO events (
                        event_type, site_id, product_id, variant_id, occurred_at,
                        previous_value, current_value, payload
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event_type.value,
                        product.site_id,
                        product.product_id,
                        variant_key,
                        observed_at,
                        old_value,
                        new_value,
                        payload,
                    ),
                )
                persisted_events.append(
                    ProductEvent(
                        event_id=cursor.lastrowid,
                        event_type=event_type,
                        product=product,
                        occurred_at=product.observed_at,
                        previous_value=old_value,
                        current_value=new_value,
                    )
                )
            connection.commit()
        return tuple(persisted_events)

    def _derive_events(
        self,
        connection: sqlite3.Connection,
        product: ProductObservation,
        variant_key: str,
        previous: sqlite3.Row | None,
        price: str | None,
        available: int | None,
        release_at: str | None,
    ) -> list[tuple[EventType, str | None, str | None]]:
        if previous is None:
            parent_exists = False
            if variant_key:
                parent_exists = (
                    connection.execute(
                        """
                        SELECT 1 FROM products
                        WHERE site_id = ? AND product_id = ?
                        LIMIT 1
                        """,
                        (product.site_id, product.product_id),
                    ).fetchone()
                    is not None
                )
            return [
                (
                    EventType.VARIANT_DISCOVERED
                    if parent_exists
                    else EventType.PRODUCT_DISCOVERED,
                    None,
                    product.variant_id or product.product_id,
                )
            ]

        events: list[tuple[EventType, str | None, str | None]] = []
        old_available = previous["available"]
        if old_available is not None and available is not None:
            if old_available == 0 and available == 1:
                events.append((EventType.RESTOCKED, "out_of_stock", "in_stock"))
            elif old_available != available:
                events.append(
                    (
                        EventType.AVAILABILITY_CHANGED,
                        "in_stock" if old_available else "out_of_stock",
                        "in_stock" if available else "out_of_stock",
                    )
                )

        if price is not None and previous["price"] != price:
            events.append((EventType.PRICE_CHANGED, previous["price"], price))
        if release_at is not None and previous["release_at"] != release_at:
            events.append(
                (EventType.RELEASE_CHANGED, previous["release_at"], release_at)
            )
        return events

    def pending_events(self, limit: int = 100) -> tuple[ProductEvent, ...]:
        if limit < 1:
            raise ValueError("limit must be positive.")
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT id, event_type, payload, occurred_at, previous_value,
                       current_value
                FROM events
                WHERE delivered_at IS NULL
                ORDER BY occurred_at, id
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return tuple(
            ProductEvent(
                event_id=row["id"],
                event_type=EventType(row["event_type"]),
                product=_observation_from_payload(row["payload"]),
                occurred_at=datetime.fromisoformat(row["occurred_at"]),
                previous_value=row["previous_value"],
                current_value=row["current_value"],
            )
            for row in rows
        )

    def mark_delivered(self, event_id: int) -> None:
        with self._connection() as connection:
            cursor = connection.execute(
                """
                UPDATE events SET delivered_at = ?
                WHERE id = ? AND delivered_at IS NULL
                """,
                (datetime.now(timezone.utc).isoformat(), event_id),
            )
            if cursor.rowcount != 1:
                raise KeyError(f"No pending event with id {event_id}.")
            connection.commit()

    def history(
        self,
        site_id: str,
        product_id: str,
        variant_id: str | None = None,
        limit: int = 100,
    ) -> tuple[ProductObservation, ...]:
        if limit < 1:
            raise ValueError("limit must be positive.")
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT payload FROM observations
                WHERE site_id = ? AND product_id = ? AND variant_id = ?
                ORDER BY observed_at DESC, id DESC
                LIMIT ?
                """,
                (site_id, product_id, variant_id or "", limit),
            ).fetchall()
        return tuple(_observation_from_payload(row["payload"]) for row in rows)

    def analytics(self) -> dict[str, int]:
        with self._connection() as connection:
            products = connection.execute(
                "SELECT COUNT(*) FROM products"
            ).fetchone()[0]
            observations = connection.execute(
                "SELECT COUNT(*) FROM observations"
            ).fetchone()[0]
            restocks = connection.execute(
                "SELECT COUNT(*) FROM events WHERE event_type = ?",
                (EventType.RESTOCKED.value,),
            ).fetchone()[0]
            pending = connection.execute(
                "SELECT COUNT(*) FROM events WHERE delivered_at IS NULL"
            ).fetchone()[0]
            event_counts = connection.execute(
                """
                SELECT event_type, COUNT(*)
                FROM events
                GROUP BY event_type
                """
            ).fetchall()
        summary = {
            "products": products,
            "observations": observations,
            "restocks": restocks,
            "pending_notifications": pending,
        }
        summary.update(
            {f"events_{row[0]}": row[1] for row in event_counts}
        )
        return summary
