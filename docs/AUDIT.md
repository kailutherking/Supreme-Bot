# Retail Monitor: repository audit and evolution roadmap

**Audit date:** 2026-11-11
**Scope:** All repository code, tests, configuration, and documentation in the current worktree. The local Supreme path change to `/shop/all/` is included and preserved.

## Executive summary

The project has moved from a single Supreme-specific script to a small,
read-only monitoring foundation. It now has typed product and query models, a
retailer plugin registry, a synchronous monitor engine, SQLite history and
change-event storage, a pending-notification outbox, an allowlisted HTTPS JSON
client, and Discord, Telegram, email, and console notification sinks.

Only the Supreme adapter is active. It uses Selenium to scan
`https://www.supremenewyork.com/shop/all/` once and emits product title, color,
URL, and an image URL when present. It does not derive price, availability,
release time, or variant data from the current page; those fields remain
unknown. Other stores are not implemented because no authorized source/API or
integration contract is identified for them.

There is no checkout, account, payment, authentication, web API, dashboard,
scheduler, or worker queue.

## Repository structure

```text
.
├── .gitignore
├── CHANGELOG.md
├── README.md
├── requirements.txt
├── supremebot.py                 # CLI, config parsing, composition root
├── docs/
│   └── AUDIT.md
├── src/
│   ├── core/
│   │   ├── monitor_engine.py     # one scan, normalize, persist, notify
│   │   ├── notifications.py     # logging, Discord, Telegram, SMTP
│   │   ├── request_engine.py    # allowlisted HTTPS JSON client
│   │   ├── site_registry.py     # RetailSite protocol and registry
│   │   └── storage.py           # SQLite products/history/events/outbox
│   ├── shared/
│   │   └── models.py            # observations, filters, events, summaries
│   └── sites/
│       └── supreme/
│           └── adapter.py       # Supreme URL, Selenium, selectors, parsing
└── tests/
    ├── test_integrations.py
    ├── test_monitoring.py
    └── test_supremebot.py
```

`.gitignore` excludes local configuration, the SQLite data directory, virtual
environments, and Python bytecode. `requirements.txt` pins Selenium 4.52.0;
all other runtime components use the Python standard library.

## Current architecture and data flow

```text
supremebot.py
  ├─ reads config.json and target filters
  ├─ registers enabled plugins (currently Supreme only)
  └─ constructs MonitorEngine
       ├─ SupremeSite -> Selenium -> one Supreme listing page
       ├─ applies shared query filters
       ├─ SQLiteStorage
       │    ├─ latest products
       │    ├─ every accepted observation
       │    ├─ derived change events
       │    └─ pending notification outbox
       └─ NotificationDispatcher
            ├─ console logging
            ├─ Discord webhook (opt-in)
            ├─ Telegram bot API (opt-in)
            └─ SMTP email (opt-in)
```

The `RetailSite` protocol accepts a `MonitorQuery` and returns normalized
`ProductObservation` values. The engine validates plugin/site identity,
applies filters, stores history and change events, then delivers pending
notifications. The core is synchronous and the CLI executes one scan per
invocation.

## Current capabilities

| Area | Implemented behavior | Boundary |
|---|---|---|
| Product discovery | Supreme listing page scanned once | Requires Selenium, Chrome, and current page selectors |
| Keyword/color monitoring | Shared filter model; multiple target rules are ORed, words within a rule are ANDed | CLI config currently supports keywords and color only |
| Collection monitoring | `collection_id` exists in shared query and product models | No active adapter or CLI configuration supplies collection data |
| Variants | Variant ID is part of the stored identity; new variants create events | Supreme adapter does not provide variant IDs |
| Inventory/restock | SQLite emits restock when a known `false` availability becomes `true` | Supreme adapter reports availability as unknown, so it emits no restocks |
| Price/release changes | SQLite records and detects changes when an adapter supplies those fields | Supreme adapter currently supplies neither |
| History | SQLite stores every accepted observation and event | No retention/compaction policy or migration framework |
| Analytics | Basic product, observation, restock, and pending-event counts | No time-series queries, CLI report, dashboard, or latency metrics |
| Notifications | Console, Discord, Telegram, SMTP email | Provider setup is environment-based; no SMS, user preferences, or per-channel delivery receipts |
| Request layer | HTTPS JSON client enforces exact allowed hosts, request spacing, timeout, response size, and no redirects | No current site adapter calls it; it has no cache or retry policy |

### Repository audit details

- **API usage:** No external retailer API is currently called. The Supreme
  adapter uses Selenium and DOM selectors. `AuthorizedJsonClient` is a guarded
  foundation for a future documented, authorized API/feed plugin.
- **Dependencies:** Selenium 4.52.0 is the only declared dependency. There is
  no complete transitive lockfile, package metadata, CI workflow, or automated
  dependency vulnerability scan.
- **Configuration:** `config.json` is created in the working directory with
  target keywords, color, headless mode, and a SQLite path. Unsupported fields
  such as credentials and checkout settings are rejected. Notification
  credentials are read from environment variables.
- **Logging:** Python's standard `logging` module writes to stdout. Product
  events are sent through the logging notifier; provider errors are reported
  without including webhook/token values.
- **Output formats:** Human-readable console logs; SQLite tables for
  normalized products, observations, events, and delivery status. There is no
  JSON/CSV export or HTTP API.
- **Tests:** Unit/integration tests cover config validation, filters, SQLite
  history/change detection, the monitor engine, request restrictions, and
  mocked Discord/Telegram/email behavior. They do not launch a browser, contact
  a retailer, or send real notifications.
- **Security/data:** The database contains product metadata only. Config file
  defaults are owner-only on POSIX. Notification secrets must not be committed
  or logged. The application stores no payment or customer data.

## What works well

- Site-specific browser and DOM logic is isolated from shared filtering,
  storage, and notification code.
- Product and event types are explicit, and the engine checks the site ID
  returned by each plugin.
- SQLite persistence distinguishes current product state from observation
  history and derived events.
- Notification events are persisted before delivery. A failed delivery leaves
  the event pending for a later scan rather than silently discarding it.
- The JSON request client is restricted to HTTPS and an explicit host allowlist,
  with a configurable interval, timeout, response-size cap, and redirects
  disabled.
- Credentials are opt-in through environment variables; outgoing notification
  content is limited to product information.
- Tests use local databases and mocked transports, avoiding uncontrolled
  network or retailer activity.

## Technical debt, reliability, and scalability limits

1. **Single retailer and brittle selectors.** Supreme is the only active
   adapter. CSS class names and listing structure can change without notice.
   The integration has not been tested against a live page.
2. **No verified inventory signal.** Presence on the listing page is not proof
   of availability. The adapter correctly records availability as unknown;
   restock metrics will remain empty until a permitted source reports stock.
3. **One-shot execution.** There is no scheduler, task lifecycle, cancellation,
   backpressure, concurrency limit, or worker health check.
4. **SQLite is single-host storage.** WAL and a busy timeout help local use but
   do not make SQLite a multi-host database. There is no schema versioning,
   retention job, backup/restore test, or operational migration path.
5. **Notification outbox is at-least-once.** Events are marked delivered after
   all configured sinks return successfully. If one sink succeeds and a later
   sink fails, a subsequent run may deliver a duplicate to the successful
   sink. There are no per-sink receipts or exponential retry schedule.
6. **Metrics are minimal.** Counts exist, but there are no latency, queue age,
   provider-delivery, source error-rate, or per-site budget metrics.
7. **No deployment boundary.** The CLI is the only entry point. There is no
   service API, authentication, dashboard, secrets manager, CI, or deployment
   configuration.
8. **Operational source policy is not yet a registry.** The request client
   supports an exact host allowlist, but active plugins still need documented
   source permissions, request budgets, attribution, and data-retention rules.

No evidence of a memory leak or concurrency race was found in the current
single-scan path. Browser cleanup is in `finally`; unexpected database and
plugin errors remain visible rather than being converted to success-shaped
results.

## Retailer plugin architecture

The protocol is deliberately small:

```python
class RetailSite(Protocol):
    @property
    def site_id(self) -> str: ...

    def discover(
        self, query: MonitorQuery
    ) -> Iterable[ProductObservation]: ...
```

`src/sites/supreme/adapter.py` is the concrete example. A new plugin should
normalize source records into `ProductObservation` and declare its source,
permitted request budget, supported fields, and error behavior. Use
`AuthorizedJsonClient` for documented, authorized HTTPS JSON sources; avoid
browser automation when a supported feed/API exists. No adapter should infer
availability from a product page being present.

The following are planned plugin slots, **not implemented integrations**:
Supreme, Kith, Nike, SNKRS, Adidas, Palace, Stussy, New Balance, Concepts,
Bodega, Union, and Undefeated. Some brands/platforms may not expose an
authorized source suitable for this monitor. Keep those sites disabled until
their documented access and limits are reviewed.

## Feature-gap analysis and competitor context

Valor, Wrath, MekAIO, Kodai, Cyber, and Balko are proprietary products. This
repository has no source-verified competitor research, so this report does
not attribute specific features or internals to those vendors. The comparison
below is against common retail-monitoring platform capabilities, not claims
about any named product.

| Capability area | Current project | Gap to a mature monitoring/intelligence service |
|---|---|---|
| Multi-site discovery | One Supreme listing adapter | Authorized adapter per retailer, source contracts, versioning, health checks |
| Product/release discovery | One current listing scan | Feed/collection/keyword sources, scheduled discovery, release calendar and change history |
| Restock and inventory intelligence | Event model supports known availability transitions | Reliable source signals, variant-level inventory, deduplication and time-window analytics |
| Price intelligence | Price-change event and history fields | Currency normalization, price histories, alert thresholds and analytics queries |
| Notifications | Discord, Telegram, email transports | Per-user routing/preferences, templates, retries, rate limits and delivery receipts |
| Analytics | Basic aggregate counts | Time-series latency, discovery/restock rates, source health, error budgets and dashboards |
| Operations | Synchronous local CLI | Durable jobs, cancellation, bounded queues, worker orchestration and service monitoring |
| Storage | Local SQLite history | PostgreSQL-backed shared state, migrations, retention, backup/restore and tenant boundaries |

## Recommended folder structure as the platform grows

```text
src/
  core/
    monitor_engine.py
    request_engine.py
    site_registry.py
    storage.py
    notifications.py
    analytics.py                 # planned: queryable time-series/reporting
  shared/
    models.py
    config.py                    # planned: versioned config schema
    policies.py                  # planned: per-source budget/retention rules
  sites/
    supreme/
      adapter.py                 # implemented
    kith/                         # future, authorized source required
    nike/
    snkrs/
    adidas/
    palace/
    stussy/
    new_balance/
    concepts/
    bodega/
    union/
    undefeated/
  api/                            # future authenticated API
  ui/                             # future React dashboard
tests/
docs/
```

Parsing remains site-owned unless multiple adapters demonstrably share a
stable format. Keep retailer-specific assumptions out of the core.

## Storage recommendation

- **SQLite (implemented):** local single-process development, product state,
  observations, change events, and pending notifications. Add schema migrations,
  retention, and backup/restore tests before treating the database as
  operationally durable.
- **PostgreSQL (next for shared service):** authoritative product/event/task
  storage when multiple workers or users need shared transactional state.
  Add versioned migrations, indexes, retention, access control, and backups.
- **Redis (later, optional):** ephemeral queue coordination, short-lived
  deduplication keys, and rate-limit counters only when a measured workload
  requires it. Do not make it the sole record of product history.

Do not store payment data, browser cookies, or unnecessary personal data in
any of these stores.

## Notification improvements

Implemented environment variables:

| Provider | Required variables |
|---|---|
| Discord | `DISCORD_WEBHOOK_URL` |
| Telegram | `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` |
| Email | `SMTP_HOST`, `EMAIL_FROM`, `EMAIL_TO`; optional `SMTP_PORT` (587 default), `SMTP_USERNAME`, `SMTP_PASSWORD` |

Messages include product title, site, price/availability when known, product
URL, and image when available. Telegram credentials must be configured as a
pair; SMTP credentials must be configured as a pair. Notification sends are
explicitly opt-in. The remaining reliability step is per-sink outbox tracking
and bounded retry/backoff.

## Future React dashboard and scale-up roadmap

```text
React dashboard
      |
Authenticated API + authorization/audit
      |
PostgreSQL <----> task and analytics services
      |
Bounded monitor workers ----> retailer plugins ----> approved feeds/APIs
      |                              |
      +----> event outbox ----------+----> notification providers

Optional Redis: ephemeral queue/cache/rate-limit coordination only
```

The API should own user/task configuration and enforce tenant access. Workers
should use the same plugin and observation contracts as the current CLI. Never
allow a dashboard user to supply arbitrary request hosts; adapter source
allowlists and published request budgets remain server-controlled.

### Phase 1 — source quality and operations

1. Choose one retailer with documented permitted access and implement a
   fixture-tested adapter; do not activate unverified targets.
2. Add source-specific request budgets, conditional requests where supported,
   schema/version checks, and adapter health metrics.
3. Add SQLite schema migrations, retention, duplicate/outbox delivery tests,
   and a CLI analytics report.

### Phase 2 — shared monitoring service

1. Add a backend API around the same monitor/storage interfaces.
2. Move shared state to PostgreSQL; add a bounded worker queue only when
   measured volume requires it.
3. Add authentication, authorization, audit logging, per-user notification
   preferences, and explicit data-retention controls.
4. Add Redis only for measured ephemeral coordination/cache needs.

### Phase 3 — React UI

Build a React frontend for monitor configuration, product history, release and
inventory reports, analytics, source health, and notification preferences.
The UI should call the authenticated API; it should not access retailer
credentials or retailer sources directly. Checkout, payment, and purchasing
remain out of scope.

## Current scorecard

| Area | Score | Main blocker |
|---|---:|---|
| Architecture | 5/10 | Reusable core exists, but only one adapter and no service/API boundary |
| Maintainability | 6/10 | Models/tests exist; no package metadata, CI, config schema version, or DB migrations |
| Performance | 4/10 | Single browser startup per run; no source cache or measured workload |
| Scalability | 3/10 | SQLite and synchronous execution are local/single-process |
| Reliability | 5/10 | Cleanup and outbox exist; no scheduler, per-sink delivery receipts, or live adapter tests |
| Security | 7/10 | Read-only and no payment data; still needs dependency scanning, deployment controls, and source review |
| Extensibility | 5/10 | Plugin interface exists; only Supreme is implemented |
| Modernity | 5/10 | Typed Python modules and tests; no API, UI, CI, or operational telemetry |

Scores are for the current prototype, not a production deployment. Raising them
requires authorized source integrations, operational tests, migrations,
monitoring, and a reviewed deployment model.
