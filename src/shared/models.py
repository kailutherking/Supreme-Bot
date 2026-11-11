from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from urllib.parse import urlparse


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class ProductObservation:
    site_id: str
    product_id: str
    title: str
    url: str
    observed_at: datetime = field(default_factory=utc_now)
    variant_id: str | None = None
    color: str | None = None
    image_url: str | None = None
    price: Decimal | None = None
    currency: str | None = None
    available: bool | None = None
    collection_id: str | None = None
    release_at: datetime | None = None

    def __post_init__(self) -> None:
        for field_name in ("site_id", "product_id", "title", "url"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must be a non-empty string.")

        for field_name in ("variant_id", "color", "image_url", "currency", "collection_id"):
            value = getattr(self, field_name)
            if value is not None and not isinstance(value, str):
                raise ValueError(f"{field_name} must be a string or None.")

        self._validate_https_url(self.url, "url")
        if self.image_url is not None:
            self._validate_https_url(self.image_url, "image_url")
        if self.price is not None:
            if not isinstance(self.price, Decimal):
                raise ValueError("price must be a Decimal.")
            if not self.price.is_finite() or self.price < Decimal("0"):
                raise ValueError("price must be a finite, non-negative decimal.")
        if self.currency is not None:
            if len(self.currency) != 3 or not self.currency.isascii() or not self.currency.isalpha():
                raise ValueError("currency must be a three-letter code.")
        if self.available is not None and not isinstance(self.available, bool):
            raise ValueError("available must be true, false, or unknown.")
        object.__setattr__(
            self, "observed_at", self._as_utc(self.observed_at, "observed_at")
        )
        if self.release_at is not None:
            object.__setattr__(
                self, "release_at", self._as_utc(self.release_at, "release_at")
            )

    @staticmethod
    def _validate_https_url(value: str, field_name: str) -> None:
        parsed = urlparse(value)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
        ):
            raise ValueError(f"{field_name} must be an absolute HTTPS URL.")

    @staticmethod
    def _as_utc(value: datetime, field_name: str) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError(f"{field_name} must include a timezone.")
        return value.astimezone(timezone.utc)


@dataclass(frozen=True)
class ProductFilter:
    keywords: tuple[str, ...] = ()
    color: str | None = None

    def matches(self, product: ProductObservation) -> bool:
        title = product.title.casefold()
        if not all(keyword.casefold() in title for keyword in self.keywords):
            return False
        if self.color is not None and (
            product.color is None
            or self.color.casefold() not in product.color.casefold()
        ):
            return False
        return True


@dataclass(frozen=True)
class MonitorQuery:
    filters: tuple[ProductFilter, ...] = ()
    collection_id: str | None = None

    def matches(self, product: ProductObservation) -> bool:
        if self.collection_id is not None and (
            product.collection_id != self.collection_id
        ):
            return False
        return not self.filters or any(
            product_filter.matches(product) for product_filter in self.filters
        )


class EventType(str, Enum):
    PRODUCT_DISCOVERED = "product_discovered"
    VARIANT_DISCOVERED = "variant_discovered"
    RESTOCKED = "restocked"
    AVAILABILITY_CHANGED = "availability_changed"
    PRICE_CHANGED = "price_changed"
    RELEASE_CHANGED = "release_changed"


@dataclass(frozen=True)
class ProductEvent:
    event_id: int | None
    event_type: EventType
    product: ProductObservation
    occurred_at: datetime
    previous_value: str | None = None
    current_value: str | None = None


@dataclass(frozen=True)
class ScanSummary:
    sites_scanned: int
    products_observed: int
    events_created: int
    notifications_delivered: int
