from __future__ import annotations

from collections.abc import Iterable, Iterator
from typing import Protocol

from src.shared.models import MonitorQuery, ProductObservation


class RetailSite(Protocol):
    @property
    def site_id(self) -> str: ...

    def discover(self, query: MonitorQuery) -> Iterable[ProductObservation]: ...


class SiteRegistry:
    def __init__(self) -> None:
        self._sites: dict[str, RetailSite] = {}

    def register(self, site: RetailSite) -> None:
        site_id = site.site_id.strip().casefold()
        if not site_id:
            raise ValueError("A site plugin must have a non-empty site_id.")
        if site_id in self._sites:
            raise ValueError(f"A plugin for {site_id!r} is already registered.")
        self._sites[site_id] = site

    def get(self, site_id: str) -> RetailSite:
        try:
            return self._sites[site_id.strip().casefold()]
        except KeyError:
            raise KeyError(f"No plugin is registered for {site_id!r}.") from None

    def __iter__(self) -> Iterator[RetailSite]:
        for site_id in sorted(self._sites):
            yield self._sites[site_id]

    def __len__(self) -> int:
        return len(self._sites)
