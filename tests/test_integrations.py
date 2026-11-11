import json
from datetime import datetime, timezone
from decimal import Decimal
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from src.core.notifications import (
    DiscordWebhookNotifier,
    EmailNotifier,
    NotificationError,
    TelegramNotifier,
    notifiers_from_environment,
)
from src.core.request_engine import AuthorizedJsonClient, RequestError
from src.shared.models import EventType, ProductEvent, ProductObservation


class _Response:
    def __init__(self, body=b"", status=200):
        self.body = body
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        del exc_type, exc_value, traceback
        return False

    def read(self, size=-1):
        return self.body[:size]


class _Opener:
    def __init__(self, response):
        self.response = response
        self.request = None
        self.timeout = None

    def open(self, request, timeout):
        self.request = request
        self.timeout = timeout
        return self.response


def _event():
    product = ProductObservation(
        site_id="sample",
        product_id="sku-1",
        title="Canvas Jacket",
        url="https://shop.example/products/sku-1",
        image_url="https://cdn.example/sku-1.jpg",
        price=Decimal("125.00"),
        currency="USD",
        available=True,
    )
    return ProductEvent(
        event_id=1,
        event_type=EventType.RESTOCKED,
        product=product,
        occurred_at=datetime.now(timezone.utc),
        previous_value="out_of_stock",
        current_value="in_stock",
    )


class AuthorizedJsonClientTests(unittest.TestCase):
    def test_requires_an_allowed_https_host_and_parses_json(self):
        opener = _Opener(_Response(b'{"products": []}'))
        with patch("src.core.request_engine.build_opener", return_value=opener):
            client = AuthorizedJsonClient(
                ["api.example"], minimum_interval=0, user_agent="MonitorTest/1.0"
            )
            self.assertEqual(
                client.get_json("https://api.example/catalog"),
                {"products": []},
            )
            self.assertEqual(opener.request.get_header("User-agent"), "MonitorTest/1.0")
            with self.assertRaisesRegex(ValueError, "authorized host"):
                client.get_json("https://other.example/catalog")
            with self.assertRaisesRegex(ValueError, "HTTPS"):
                client.get_json("http://api.example/catalog")
            with self.assertRaisesRegex(ValueError, "authorized host"):
                client.get_json("https://user:pass@api.example/catalog")
            with self.assertRaisesRegex(ValueError, "authorized host"):
                client.get_json("https://api.example:8443/catalog")

    def test_rejects_oversized_response(self):
        opener = _Opener(_Response(b'{"long":"body"}'))
        with patch("src.core.request_engine.build_opener", return_value=opener):
            client = AuthorizedJsonClient(
                ["api.example"],
                minimum_interval=0,
                maximum_response_bytes=4,
            )
            with self.assertRaisesRegex(RequestError, "size limit"):
                client.get_json("https://api.example/catalog")


class NotificationTests(unittest.TestCase):
    def test_environment_configuration_is_opt_in_and_validated(self):
        dispatcher = notifiers_from_environment({})
        self.assertEqual([sink.sink_id for sink in dispatcher.sinks], ["log"])
        with self.assertRaisesRegex(ValueError, "configured together"):
            notifiers_from_environment({"TELEGRAM_BOT_TOKEN": "token"})
        with self.assertRaisesRegex(ValueError, "missing EMAIL_TO"):
            notifiers_from_environment({"SMTP_HOST": "smtp.example", "EMAIL_FROM": "a@example"})

    def test_discord_notification_contains_product_metadata_and_image(self):
        notifier = DiscordWebhookNotifier(
            "https://discord.com/api/webhooks/example/secret"
        )
        with patch(
            "src.core.notifications.urlopen", return_value=_Response(status=204)
        ) as open_url:
            notifier.send(_event())

        request = open_url.call_args.args[0]
        payload = json.loads(request.data)
        embed = payload["embeds"][0]
        self.assertEqual(embed["title"], "Canvas Jacket")
        self.assertEqual(embed["url"], "https://shop.example/products/sku-1")
        self.assertEqual(embed["thumbnail"]["url"], "https://cdn.example/sku-1.jpg")
        self.assertIn("USD 125.00", [field["value"] for field in embed["fields"]])

    def test_telegram_notification_checks_api_result(self):
        notifier = TelegramNotifier("secret-token", "chat-1")
        with patch(
            "src.core.notifications.urlopen",
            return_value=_Response(b'{"ok": true}', status=200),
        ) as open_url:
            notifier.send(_event())
        self.assertIn("sendPhoto", open_url.call_args.args[0].full_url)

        with patch(
            "src.core.notifications.urlopen",
            return_value=_Response(b'{"ok": false}', status=200),
        ):
            with self.assertRaisesRegex(NotificationError, "rejected"):
                notifier.send(_event())

    def test_telegram_http_error_does_not_expose_bot_token(self):
        token = "secret-token"
        notifier = TelegramNotifier(token, "chat-1")
        error = HTTPError(
            f"https://api.telegram.org/bot{token}/sendPhoto",
            403,
            "Forbidden",
            {},
            None,
        )
        with patch("src.core.notifications.urlopen", side_effect=error):
            with self.assertRaises(NotificationError) as raised:
                notifier.send(_event())
        self.assertNotIn(token, str(raised.exception))

    def test_email_notification_contains_product_and_image_links(self):
        class FakeSMTP:
            def __init__(self):
                self.message = None

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc_value, traceback):
                del exc_type, exc_value, traceback
                return False

            def starttls(self, context):
                self.context = context

            def send_message(self, message):
                self.message = message

        smtp = FakeSMTP()
        notifier = EmailNotifier(
            "smtp.example",
            "monitor@example.com",
            "user@example.com",
        )
        with patch("src.core.notifications.smtplib.SMTP", return_value=smtp):
            notifier.send(_event())

        self.assertIn("Canvas Jacket", smtp.message["Subject"])
        self.assertIn("https://cdn.example/sku-1.jpg", smtp.message.get_body("html").get_content())
        self.assertIn("https://shop.example/products/sku-1", smtp.message.get_body("plain").get_content())


if __name__ == "__main__":
    unittest.main()
