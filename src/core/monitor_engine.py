from __future__ import annotations

from typing import Protocol

from src.core.site_registry import SiteRegistry
from src.core.storage import SQLiteStorage
from src.shared.models import MonitorQuery, ProductEvent, ScanSummary


class EventPublisher(Protocol):
    def publish(self, event: ProductEvent) -> None: ...


class MonitorEngine:
    def __init__(
        self,
        sites: SiteRegistry,
        storage: SQLiteStorage,
        notifications: EventPublisher | None = None,
    ) -> None:
        self.sites = sites
        self.storage = storage
        self.notifications = notifications
        self.storage.initialize()

    def scan_once(self, query: MonitorQuery) -> ScanSummary:
        observations = 0
        events_created = 0

        for site in self.sites:
            for product in site.discover(query):
                if product.site_id.casefold() != site.site_id.casefold():
                    raise ValueError(
                        f"Plugin {site.site_id!r} yielded a product for "
                        f"{product.site_id!r}."
                    )
                if not query.matches(product):
                    continue
                observations += 1
                events_created += len(self.storage.record(product))

        delivered = self._deliver_pending()
        return ScanSummary(
            sites_scanned=len(self.sites),
            products_observed=observations,
            events_created=events_created,
            notifications_delivered=delivered,
        )

    def _deliver_pending(self) -> int:
        if self.notifications is None:
            return 0

        delivered = 0
        for event in self.storage.pending_events():
            self.notifications.publish(event)
            if event.event_id is None:
                raise RuntimeError("Stored notification event has no event ID.")
            self.storage.mark_delivered(event.event_id)
            delivered += 1
        return delivered
