from __future__ import annotations

import html
import json
import logging
import os
import smtplib
import ssl
from collections.abc import Mapping, Sequence
from email.message import EmailMessage
from logging import Logger
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from src.shared.models import ProductEvent


class NotificationError(RuntimeError):
    pass


class NotificationSink(Protocol):
    sink_id: str

    def send(self, event: ProductEvent) -> None: ...


def _availability_text(available: bool | None) -> str:
    if available is True:
        return "In stock"
    if available is False:
        return "Out of stock"
    return "Listed; availability not reported by source"


def _price_text(event: ProductEvent) -> str:
    product = event.product
    if product.price is None:
        return "Not provided"
    return f"{product.currency or ''} {product.price}".strip()


def _variant_text(event: ProductEvent) -> str | None:
    product = event.product
    return product.variant_id or product.color


def _plain_message(event: ProductEvent) -> str:
    product = event.product
    lines = [
        f"{event.event_type.value.replace('_', ' ').title()}: {product.title}",
        f"Store: {product.site_id}",
        f"Price: {_price_text(event)}",
        f"Availability: {_availability_text(product.available)}",
    ]
    variant = _variant_text(event)
    if variant:
        lines.append(f"Variant: {variant}")
    if product.release_at:
        lines.append(f"Release: {product.release_at.isoformat()}")
    if product.image_url:
        lines.append(f"Image: {product.image_url}")
    lines.append(f"Product: {product.url}")
    return "\n".join(lines)


class NotificationDispatcher:
    def __init__(self, sinks: Sequence[NotificationSink] = ()) -> None:
        self.sinks = tuple(sinks)

    def publish(self, event: ProductEvent) -> None:
        for sink in self.sinks:
            sink.send(event)


class LoggingNotifier:
    sink_id = "log"

    def __init__(self, logger: Logger) -> None:
        self.logger = logger

    def send(self, event: ProductEvent) -> None:
        self.logger.info("%s", _plain_message(event))


class DiscordWebhookNotifier:
    sink_id = "discord"

    def __init__(self, webhook_url: str, timeout: float = 10.0) -> None:
        parsed = urlparse(webhook_url)
        if (
            parsed.scheme != "https"
            or parsed.hostname not in {"discord.com", "discordapp.com"}
            or not parsed.path.startswith("/api/webhooks/")
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("Discord webhook URL must be a Discord HTTPS webhook.")
        self._webhook_url = webhook_url
        self._timeout = timeout

    def send(self, event: ProductEvent) -> None:
        product = event.product
        embed = {
            "title": product.title[:256],
            "url": product.url,
            "description": event.event_type.value.replace("_", " ").title(),
            "fields": [
                {"name": "Store", "value": product.site_id, "inline": True},
                {"name": "Price", "value": _price_text(event), "inline": True},
                {
                    "name": "Availability",
                    "value": _availability_text(product.available),
                    "inline": True,
                },
            ],
        }
        variant = _variant_text(event)
        if variant:
            embed["fields"].append(
                {"name": "Variant", "value": variant, "inline": True}
            )
        if product.image_url:
            embed["thumbnail"] = {"url": product.image_url}
        body = json.dumps({"embeds": [embed]}).encode("utf-8")
        request = Request(
            self._webhook_url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=self._timeout) as response:
                if response.status >= 400:
                    raise NotificationError(
                        f"Discord returned HTTP {response.status}."
                    )
        except HTTPError as error:
            raise NotificationError(
                f"Discord returned HTTP {error.code}."
            ) from None
        except (URLError, TimeoutError):
            raise NotificationError("Discord notification delivery failed.") from None


class TelegramNotifier:
    sink_id = "telegram"

    def __init__(self, bot_token: str, chat_id: str, timeout: float = 10.0) -> None:
        if not bot_token.strip() or not chat_id.strip():
            raise ValueError("Telegram bot token and chat ID are required.")
        self._endpoint = f"https://api.telegram.org/bot{bot_token}/"
        self._chat_id = chat_id
        self._timeout = timeout

    def send(self, event: ProductEvent) -> None:
        product = event.product
        message = "\n".join(
            (
                f"<b>{html.escape(event.event_type.value.replace('_', ' ').title())}</b>",
                f"<b>{html.escape(product.title)}</b>",
                f"Store: {html.escape(product.site_id)}",
                f"Price: {html.escape(_price_text(event))}",
                f"Availability: {html.escape(_availability_text(product.available))}",
                (
                    f"Variant: {html.escape(_variant_text(event))}"
                    if _variant_text(event)
                    else ""
                ),
                (
                    f'<a href="{html.escape(product.url, quote=True)}">'
                    "Open product</a>"
                ),
            )
        )
        action = "sendPhoto" if product.image_url else "sendMessage"
        fields = {
            "chat_id": self._chat_id,
            "parse_mode": "HTML",
        }
        if product.image_url:
            fields["photo"] = product.image_url
            fields["caption"] = message
        else:
            fields["text"] = message
        request = Request(
            self._endpoint + action,
            data=urlencode(fields).encode("utf-8"),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=self._timeout) as response:
                if response.status >= 400:
                    raise NotificationError(
                        f"Telegram returned HTTP {response.status}."
                    )
                result = json.loads(response.read(64_000))
                if not isinstance(result, dict) or result.get("ok") is not True:
                    raise NotificationError("Telegram rejected the notification.")
        except HTTPError as error:
            raise NotificationError(
                f"Telegram returned HTTP {error.code}."
            ) from None
        except (URLError, TimeoutError):
            raise NotificationError("Telegram notification delivery failed.") from None
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise NotificationError("Telegram returned an invalid response.") from None


class EmailNotifier:
    sink_id = "email"

    def __init__(
        self,
        host: str,
        sender: str,
        recipient: str,
        *,
        port: int = 587,
        username: str | None = None,
        password: str | None = None,
        timeout: float = 10.0,
    ) -> None:
        if not host or not sender or not recipient:
            raise ValueError("Email host, sender, and recipient are required.")
        if (username is None) != (password is None):
            raise ValueError("SMTP username and password must be set together.")
        if not 1 <= port <= 65535:
            raise ValueError("SMTP port must be between 1 and 65535.")
        self._host = host
        self._sender = sender
        self._recipient = recipient
        self._port = port
        self._username = username
        self._password = password
        self._timeout = timeout

    def send(self, event: ProductEvent) -> None:
        product = event.product
        message = EmailMessage()
        message["Subject"] = (
            f"{event.event_type.value.replace('_', ' ').title()}: {product.title}"
        )
        message["From"] = self._sender
        message["To"] = self._recipient
        message.set_content(_plain_message(event))

        html_body = (
            f"<h2>{html.escape(product.title)}</h2>"
            f"<p>Store: {html.escape(product.site_id)}<br>"
            f"Price: {html.escape(_price_text(event))}<br>"
            f"Availability: {html.escape(_availability_text(product.available))}<br>"
            f"Variant: {html.escape(_variant_text(event) or 'Not provided')}</p>"
            f'<p><a href="{html.escape(product.url, quote=True)}">Open product</a></p>'
        )
        if product.image_url:
            html_body += (
                f'<p><img src="{html.escape(product.image_url, quote=True)}" '
                f'alt="{html.escape(product.title, quote=True)}"></p>'
            )
        message.add_alternative(html_body, subtype="html")

        try:
            context = ssl.create_default_context()
            if self._port == 465:
                with smtplib.SMTP_SSL(
                    self._host, self._port, timeout=self._timeout, context=context
                ) as server:
                    self._login_and_send(server, message)
            else:
                with smtplib.SMTP(
                    self._host, self._port, timeout=self._timeout
                ) as server:
                    server.starttls(context=context)
                    self._login_and_send(server, message)
        except (OSError, smtplib.SMTPException):
            raise NotificationError("Email notification delivery failed.") from None

    def _login_and_send(self, server, message: EmailMessage) -> None:
        if self._username is not None and self._password is not None:
            server.login(self._username, self._password)
        server.send_message(message)


def notifiers_from_environment(
    environment: Mapping[str, str] | None = None,
) -> NotificationDispatcher:
    values = environment if environment is not None else os.environ
    sinks: list[NotificationSink] = []

    webhook = values.get("DISCORD_WEBHOOK_URL")
    if webhook:
        sinks.append(DiscordWebhookNotifier(webhook))

    telegram_token = values.get("TELEGRAM_BOT_TOKEN")
    telegram_chat = values.get("TELEGRAM_CHAT_ID")
    if bool(telegram_token) != bool(telegram_chat):
        raise ValueError(
            "TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be configured together."
        )
    if telegram_token and telegram_chat:
        sinks.append(TelegramNotifier(telegram_token, telegram_chat))

    email_names = (
        "SMTP_HOST",
        "SMTP_PORT",
        "SMTP_USERNAME",
        "SMTP_PASSWORD",
        "EMAIL_FROM",
        "EMAIL_TO",
    )
    if any(values.get(name) for name in email_names):
        required = ("SMTP_HOST", "EMAIL_FROM", "EMAIL_TO")
        missing = [name for name in required if not values.get(name)]
        if missing:
            raise ValueError(
                "Email notification is incomplete; missing " + ", ".join(missing)
            )
        username = values.get("SMTP_USERNAME") or None
        password = values.get("SMTP_PASSWORD") or None
        try:
            port = int(values.get("SMTP_PORT", "587"))
        except ValueError:
            raise ValueError("SMTP_PORT must be an integer.") from None
        sinks.append(
            EmailNotifier(
                values["SMTP_HOST"],
                values["EMAIL_FROM"],
                values["EMAIL_TO"],
                port=port,
                username=username,
                password=password,
            )
        )

    sinks.append(LoggingNotifier(logging.getLogger("retail-monitor")))
    return NotificationDispatcher(sinks)
