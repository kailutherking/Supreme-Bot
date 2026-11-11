from __future__ import annotations

import json
import threading
import time
from collections.abc import Mapping, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import (
    HTTPRedirectHandler,
    Request,
    build_opener,
)


class RequestError(RuntimeError):
    pass


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(
        self, _request, _response, _code, _message, _headers, _new_url
    ):
        del _request, _response, _code, _message, _headers, _new_url
        return None


class AuthorizedJsonClient:
    """Bounded HTTPS JSON client for explicitly authorized API/feed hosts."""

    def __init__(
        self,
        allowed_hosts: Sequence[str],
        *,
        minimum_interval: float = 2.0,
        timeout: float = 10.0,
        maximum_response_bytes: int = 2_000_000,
        user_agent: str = "RetailMonitor/1.0",
    ) -> None:
        if not allowed_hosts:
            raise ValueError("At least one authorized host is required.")
        if minimum_interval < 0 or timeout <= 0 or maximum_response_bytes < 1:
            raise ValueError("Request limits must be positive (interval may be zero).")
        self._allowed_hosts = frozenset(
            host.strip().casefold().rstrip(".") for host in allowed_hosts
        )
        if any(not host for host in self._allowed_hosts):
            raise ValueError("Authorized host names cannot be empty.")
        self._minimum_interval = minimum_interval
        self._timeout = timeout
        self._maximum_response_bytes = maximum_response_bytes
        self._user_agent = user_agent
        self._opener = build_opener(_NoRedirect())
        self._host_lock = threading.Lock()
        self._next_request_at: dict[str, float] = {}

    def _validate_url(self, url: str) -> str:
        parsed = urlparse(url)
        hostname = (parsed.hostname or "").casefold().rstrip(".")
        try:
            port = parsed.port
        except ValueError:
            raise ValueError("URL must contain a valid port.") from None
        if (
            parsed.scheme != "https"
            or hostname not in self._allowed_hosts
            or port not in (None, 443)
            or parsed.username is not None
            or parsed.password is not None
        ):
            raise ValueError("URL must use HTTPS and an explicitly authorized host.")
        return hostname

    def _wait_for_slot(self, hostname: str) -> None:
        with self._host_lock:
            now = time.monotonic()
            wait = self._next_request_at.get(hostname, now) - now
            if wait > 0:
                time.sleep(wait)
            self._next_request_at[hostname] = (
                time.monotonic() + self._minimum_interval
            )

    def get_json(
        self, url: str, headers: Mapping[str, str] | None = None
    ) -> object:
        hostname = self._validate_url(url)
        self._wait_for_slot(hostname)
        request_headers = {"Accept": "application/json", "User-Agent": self._user_agent}
        if headers:
            if any(name.casefold() == "host" for name in headers):
                raise ValueError("The Host header cannot be overridden.")
            request_headers.update(headers)
        request = Request(url, headers=request_headers, method="GET")

        try:
            with self._opener.open(request, timeout=self._timeout) as response:
                body = response.read(self._maximum_response_bytes + 1)
        except HTTPError as error:
            raise RequestError(f"Authorized source returned HTTP {error.code}.") from None
        except URLError:
            raise RequestError("Authorized source could not be reached.") from None
        except TimeoutError:
            raise RequestError("Authorized source request timed out.") from None

        if len(body) > self._maximum_response_bytes:
            raise RequestError("Authorized source response exceeded the size limit.")
        try:
            return json.loads(body)
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise RequestError("Authorized source returned invalid JSON.") from None
