# Retail Monitor

A read-only retail product monitoring prototype. The shared core normalizes
product observations, stores history and change events in SQLite, and can send
opt-in product notifications. The only active retailer adapter is Supreme;
other retailer integrations require a documented, permitted data source and
are not enabled.

The application does **not** log in, add products to carts, store payment
details, submit orders, solve challenges, rotate proxies, or bypass site
protections. Product links are for manual review.

## Current capabilities

- One-shot product listing discovery and keyword/color filtering.
- A retailer plugin protocol and registry.
- SQLite persistence for current products, observations, change history, and
  pending notification events.
- Change detection for first discovery, new variants, restocks, availability,
  price, and release-time changes when a source provides those fields.
- Opt-in Discord webhook, Telegram bot, and SMTP email notifications.
- A bounded HTTPS JSON client for future explicitly authorized API/feed
  adapters. The Supreme adapter currently uses Selenium and does not use this
  API client.

The Supreme page currently provides listing title, color, URL, and sometimes
an image. It does not expose a verified price, variant, or inventory state to
this adapter, so those values remain unknown and no restock/price events are
inferred from listing presence alone.

## Requirements and installation

- Python 3.10 or newer
- Google Chrome installed locally for the active Supreme adapter
- Network access to the authorized source you configure

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

The runtime dependency is Selenium 4.52.0. Selenium Manager handles browser
driver setup. SQLite and the notification transports use the Python standard
library.

## Configure and run

Run once to create a safe `config.json` template:

```bash
python supremebot.py
```

The generated config file is owner-only on POSIX systems. Add a target and
rerun:

```json
{
  "target_items": [
    {
      "keywords": ["Faux", "Jacket"],
      "color": "Red"
    }
  ],
  "settings": {
    "headless": false,
    "database_path": "data/retail-monitor.sqlite3"
  }
}
```

All target keywords must occur in the product title; color is matched
case-insensitively when the source provides it. Multiple target entries are
ORed. A scan runs once and exits. On a first scan, each matching product is
recorded as a discovery. Open its URL yourself to confirm availability and
variant.

The shared query model also supports collection IDs for future adapters, but
the current CLI schema and Supreme adapter do not configure or populate
collections.

The program logs progress to stdout and stores non-sensitive product
observations and events in the configured SQLite database. `config.json` and
`data/` are excluded from Git. Relative database paths are resolved from the
current working directory.

Exit codes:

- `0`: scan completed, or the default config was created.
- `1`: source timed out or notification delivery failed (failed events remain
  pending in SQLite).
- `2`: invalid config, no targets configured, or Selenium is unavailable.

## Notifications

Notification providers are opt-in. Set provider environment variables before
running; credentials are not stored in `config.json`.

### Discord

```bash
export DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/..."
```

### Telegram

```bash
export TELEGRAM_BOT_TOKEN="..."
export TELEGRAM_CHAT_ID="..."
```

Both Telegram variables are required together.

### Email

```bash
export SMTP_HOST="smtp.example.com"
export SMTP_PORT="587"
export SMTP_USERNAME="..."
export SMTP_PASSWORD="..."
export EMAIL_FROM="monitor@example.com"
export EMAIL_TO="you@example.com"
```

Email uses STARTTLS by default; port `465` uses SMTP over TLS. Username and
password must either both be set or both be omitted. Provider failures are
reported and the event remains in the SQLite notification outbox. Delivery is
at-least-once across multiple providers, so a provider that already accepted a
message may receive a duplicate if another provider fails before the event is
marked delivered.

Notifications contain only product metadata and URLs. Keep provider credentials
private, restrict webhook access, and do not put secrets in source control.

## Architecture

```text
CLI + JSON config
       |
       v
MonitorEngine -> SiteRegistry -> SupremeSite plugin -> Selenium -> listing page
       |                |
       |                +-> future retailer plugins / authorized JSON feeds
       v
SQLite: products, observations, events, notification outbox
       |
       v
NotificationDispatcher -> stdout / Discord / Telegram / email
```

The reusable contracts and storage live under `src/core/` and `src/shared/`;
retailer-specific parsing is isolated under `src/sites/`. Only
`src/sites/supreme/` is currently implemented. See [docs/AUDIT.md](docs/AUDIT.md)
for the full audit, competitor-category gap analysis, proposed folder layout,
and scale-up roadmap.

## Tests

```bash
python -m unittest discover -s tests -v
```

Tests use temporary SQLite databases and mocked notification transports; they
do not contact retailer sites or send real notifications.

## Limitations and future deployment

This is a local, synchronous, one-shot CLI prototype, not a daemon or hosted
service. It has no authentication, API, React dashboard, scheduler, task queue,
PostgreSQL/Redis integration, retention job, or live multi-site adapters.
SQLite is appropriate for local single-process use; use PostgreSQL for shared
multi-worker state and Redis only for measured ephemeral queue/cache needs.
Any new adapter should use documented, authorized sources, enforce source
budgets, and stop rather than evade access controls.
