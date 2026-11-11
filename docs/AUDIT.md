# Supreme Bot: codebase audit and safe modernization plan

**Audit date:** 2026-11-11
**Scope:** All tracked repository files on `main` at the audit baseline. At that point, only [`supremebot.py`](../supremebot.py) was tracked; the audit identified no dependency manifest, tests, configuration templates, services, or UI. The baseline source compiled successfully with `python3 -m py_compile supremebot.py`. Pylance initially reported unresolved imports for `requests`, `selenium`, and `webdriver_manager`, plus unused imports for `requests` and `os`.

## Remediation update

The findings and scores below describe the initial source snapshot before remediation. The runtime has since been reduced to a one-shot, read-only listing monitor:

- Removed cart, checkout, payment-form, and automatic order-submission code; removed browser fingerprint/anti-detection modifications and human-mimic delays.
- Replaced the billing/proxy/checkout configuration with validated monitoring-only settings. New config files are created with owner-only permissions; legacy payment and checkout fields are rejected.
- Removed the size fallback behavior by no longer selecting or purchasing variants. A listing match is only a discovery; the user must open the retailer page and verify availability and variant.
- Added guaranteed driver cleanup with `finally`, clear malformed-config errors, focused tests, and a Selenium dependency declaration.
- The monitor remains Supreme-only and depends on the retailer's listing markup. Selenium 4.52.0 is pinned and installed in the selected Pylance environment; diagnostics are clean. No live retailer/browser integration test was run.
- Multi-site connectors, task queues, database, notifications, and dashboards remain unimplemented because no authorized retailer data sources or access agreements are specified.

## Executive summary

The initial source was a single-process Selenium script that combined configuration creation, browser startup, product matching, cart operations, payment-form entry, order submission, logging, and teardown in one `SupremeBot` class. It has been reduced to a one-shot, read-only Supreme listing monitor. Most platform capabilities (accounts, tasks, monitoring loops, notifications, analytics, persistence, APIs, and site adapters) still do not exist.

The most important remaining blockers are the single-site implementation, unavailable retailer-authorized data-source integration, no validated dependency lock, and no UI, storage, notifications, or metrics. The audit findings and scorecard below preserve the baseline assessment so the original risks and requested roadmap remain traceable.

This audit does **not** implement or recommend scaling automated checkout, CAPTCHA solving/bypass, proxy rotation for evading retailer controls, or browser fingerprint concealment. A responsible platform direction is limited to documented, authorized product feeds/APIs, conservative rate limits, clear stop conditions, and user-directed checkout on the retailer's own site.

## 1. Critical problems

| Finding | Evidence | Impact |
|---|---|---|
| Payment and personal data are modeled as ordinary JSON configuration | `load_config()` creates `billing_info`; `fill_checkout_form()` reads name, address, phone, card number, expiry, and CVV (`supremebot.py:32-72, 245-300`) | A real config can expose highly sensitive data through plaintext files, backups, sync, or accidental sharing. The defaults are examples, not evidence that real credentials are present. |
| Browser anti-detection behavior is explicitly configured | Chrome automation flag suppression, a fixed user agent, and a `navigator.webdriver` override (`supremebot.py:80-99`) | Evades retailer bot controls and creates brittle, policy-sensitive behavior. Remove rather than generalize this behavior. |
| Generated configuration enables automatic checkout | `auto_checkout` defaults to `True`; `submit_order()` clicks the final button when enabled (`supremebot.py:68-72, 303-331`) | Unattended purchases can occur. The code does not perform an explicit human confirmation at the point of purchase. |
| Success is reported without verifying order acceptance | `submit_order()` returns success immediately after `.click()`; `run()` then logs “Checkout completed successfully” (`supremebot.py:303-331, 333-382`) | Rejections, payment failures, unavailable inventory, or a stale page can be misreported as successful orders. |

## 2. High-priority fixes

1. **Stop collecting payment data.** Do not store card numbers/CVV in app configuration or logs. For an authorized commerce workflow, use the retailer's hosted checkout and have the user complete payment there.
2. **Remove anti-detection code.** Do not disguise automation or alter browser fingerprints. Use official documented interfaces and honor their published policies and limits.
3. **Make actions explicit and user-driven.** Replace automatic order submission with a safe handoff; do not make automated purchase submission a configurable default.
4. **Validate configuration at startup.** `load_config()` only handles `FileNotFoundError`; malformed JSON, missing keys, wrong types, and invalid delay ranges can raise uncaught exceptions or fail later with `KeyError`.
5. **Guarantee cleanup.** `driver.quit()` is reached only on the normal path. An exception in startup/run or a blocked `input()` can leave the browser process open. Use a lifecycle boundary that always closes owned resources.
6. **Use structured logging and explicit outcomes.** Distinguish discovery, timeout, user handoff, and verified result. Avoid saying that an order succeeded unless an authoritative confirmation was observed.
7. **Declare and lock dependencies.** There is no manifest or lockfile. Runtime ChromeDriver installation is implicit and can fail or change independently. The current editor environment cannot resolve Selenium or webdriver-manager imports.

## 3. Current architecture and feature inventory

| Area | Observed implementation | Status / gap |
|---|---|---|
| Project structure | One tracked Python file | No package boundaries, tests, CI, docs beyond console instructions, or configuration schema |
| Retailer support | Supreme URL and selectors are embedded in `SupremeBot` | No plugin boundary; every other requested retailer is unsupported |
| Product monitoring | Opens `/shop/all/jackets`, waits for `.inner-article`, scans current page | One-shot page scan; no schedule, restock/keyword/variant/feed/API/sitemap/collection monitoring or deduplication |
| Checkout | Selenium cart, billing/payment form fill, submit | Tightly coupled to one page flow; brittle selectors; no safe orchestration, state machine, or confirmation verification |
| Browser/session | New Chrome driver in setup; no cookie/session persistence | No pooling, lifecycle manager, session abstraction, or resource budgeting |
| Accounts/profiles | None | Billing data is embedded in a generic config object; no account or profile model |
| CAPTCHA/challenges | None | No challenge detection or safe user handoff |
| Proxies | `proxies: []` configuration field | No proxy implementation, validation, health, stickiness, or use |
| Notifications | Console and timestamped text file only | No Discord, Telegram, email, or SMS integration |
| Storage | JSON config and append-only text log | No task, event, result, or analytics store |
| Analytics | None | No counters, latency, conversion, or monitoring metrics |
| Task engine/API/UI | A synchronous `run()` loop | No task lifecycle, queue, cancellation, concurrency limits, API, or dashboard |

## 4. Scalability problems

- One browser is created for the process; work is sequential and has no independent task model.
- The site, selectors, data model, and checkout assumptions are hard-coded into a single class.
- There is no work queue, concurrency limit, backpressure, deduplication, or multi-worker coordination.
- There is no durable task state or event history; a restart loses progress.
- A Selenium browser per monitoring job would be expensive and unnecessary for documented feed/API integrations.
- There are no retailer-specific policy/rate-limit settings or per-source circuit breakers.

**Recommendation:** begin with a single-process, read-only monitoring service using authorized sources. Add persistence and a queue only when measured load and permitted access require them. Do not equate retailer count with permission to poll or automate each site.

## 5. Security and privacy review

- **Secrets and PCI scope:** generated config includes card-number and CVV fields and a sample-like value. Do not put real payment credentials in JSON, source control, logs, or analytics. Prefer retailer-hosted checkout and minimize the app's sensitive-data footprint.
- **Personal data:** name, email, phone, and address fields are collected. No retention policy, encryption-at-rest strategy, access controls, or deletion workflow exists.
- **Automation evasion:** fingerprint changes and stealth options should be removed. They are unnecessary for authorized feed access and undermine transparency.
- **Supply chain:** no pinned dependencies, lockfile, integrity policy, or vulnerability update process. `webdriver_manager` downloads a driver at runtime.
- **Configuration trust:** config is loaded without schema validation or restrictive file permissions.
- **Error visibility:** broad page-flow assumptions and incomplete exception coverage can hide failures; no redaction policy is defined.
- **Logging:** current messages do not intentionally log card fields, but free-form messages and future changes have no redaction boundary.
- **Exposure assessment:** no server, network listener, database, or API is present in the repository. This is a source review, not a penetration test or a claim that external services are secure.

## 6. Reliability risks

- `select_size()` silently chooses the first non-placeholder size when the requested size is absent (`supremebot.py:162-191`), which can lead to the wrong item variant.
- `select_size()` treats some missing-size conditions as success, so downstream steps may proceed on an unverified assumption.
- Fixed page selectors and assumptions about Supreme's current DOM can become stale without detection.
- The script does not check inventory or cart state with a durable source of truth after each transition.
- Most failures are converted to `False`; unexpected exceptions can bypass cleanup and lose useful context.
- The `run()` loop has no cancellation, bounded retry policy, or persisted checkpoint. It also processes target items serially.
- `add_random_delay()` sleeps twice, including a fixed 2–5 second delay regardless of the configured range (`supremebot.py:114-120`), making timing hard to reason about and tests slow.
- `input()` prevents unattended shutdown in non-headless mode and can hang in non-interactive environments.

## 7. Performance report

No measured benchmark or profile exists, so performance conclusions are source-based rather than workload measurements.

- Browser startup and page rendering dominate the current Selenium flow; an official feed/API is a better fit for read-only monitoring where available.
- The flow uses fixed waits and extra sleeps rather than measuring latency or using a schedule with backoff.
- No request cache, conditional fetch, result deduplication, or telemetry prevents repeated work.
- There is no queue or concurrency control; naïvely adding parallel browsers would multiply memory/CPU use and site load.
- `requests` is imported but unused; `os` is unused. Selenium and webdriver-manager imports are unresolved in the selected Pylance environment.
- No memory leak is proven by this source alone; the concrete resource-lifecycle defect is the lack of guaranteed driver shutdown on exceptional exits.

**Measure before optimizing:** discovery latency by source, request count, timeout rate, worker memory, queue age, duplicate event rate, and shutdown completion. Use a staging/mock source rather than load-testing retailer endpoints.

## 8. Competitive feature-gap analysis

The listed products—**Wrath, Valor, MekAIO, Kodai, Cyber, Prism, Ganesh, Stellar, NSB, Balko, WhatBot, Hayha, Torpedo, Phantom, TSB, and AIOMoji**—are proprietary products. This repository contains no competitor research, and this audit did not verify current vendor features or internal architecture. It would be misleading to attribute specific capabilities or implementation choices to each product without current, attributable product documentation.

The defensible comparison is therefore a **capability gap against the market category**, not a vendor-by-vendor feature claim:

| Capability commonly expected from a mature multi-site product | This repository |
|---|---|
| Multi-site adapter registry and site-specific configuration | Absent; Supreme-specific constants/selectors |
| Task UI, scheduling, pause/cancel, and task state | Absent; one synchronous entry point |
| Monitoring event stream, deduplication, and restock history | Absent |
| Account/profile management | Absent; raw billing fields are placed in config |
| Proxy pools and challenge-solving | Not implemented; field placeholder only. This audit does not recommend evasion, proxy rotation, or CAPTCHA solving. |
| Notifications and task reporting | Absent; console/file output |
| Durable analytics and operational dashboards | Absent |
| Recovery, retry budgets, and meaningful error taxonomy | Absent |
| Supported/versioned integrations and policy-aware rate limits | Absent |

**High-level patterns worth adopting safely:** adapter isolation, explicit task lifecycle/state transitions, bounded queues, durable event records, idempotent result processing, source-specific rate limits, health/latency metrics, user-facing errors, and opt-in notifications. These are general software architecture recommendations, not claims about any named vendor's internals. A genuine vendor comparison should use each product's current official public materials and clearly label promotional claims versus independently verified behavior.

## 9. Recommended multi-site architecture

Treat each retailer as an independently versioned adapter over an **authorized, documented, read-only source** (official API, licensed feed, or other explicitly permitted integration). Avoid assuming that a listed store offers such an interface. A site with no permitted source should remain unsupported rather than being automated through evasive browser behavior.

```text
                  +------------------------------+
                  | UI / CLI (task configuration)|
                  +---------------+--------------+
                                  |
                  +---------------v--------------+
                  | Task API + lifecycle manager |
                  +---------------+--------------+
                                  |
                  +---------------v--------------+
                  | Scheduler / bounded queue    |
                  +---------------+--------------+
                                  |
             +--------------------v--------------------+
             | Monitoring engine: normalize, dedupe,   |
             | rate-limit, emit events, stop on policy |
             +--------------------+--------------------+
                                  |
                    +-------------v-------------+
                    | RetailSite adapter        |
                    | documented source only    |
                    +-------------+-------------+
                                  |
                          Authorized feed/API

       events -> storage / metrics / notifications
       user -> retailer checkout (manual handoff; outside the bot)
```

### Example target layout

```text
src/
  core/
    tasks/              # lifecycle, cancellation, bounded scheduling
    monitoring/         # query model, dedupe, source limits, events
    sites/              # adapter protocol and registry
    notifications/      # consent-based Discord/Telegram/email/SMS sinks
    storage/            # repository interfaces and migrations
    telemetry/          # metrics, traces, structured logs
  sites/
    supreme/
    kith/
    nike/
    snkrs/
    adidas_confirmed/
    ...                 # add only with an authorized source/integration
  shared/
    models/
    policies/           # retention, rate limits, data minimization
  ui/
tests/
docs/
```

The named retailers can be represented as future adapter slots: Supreme, Kith, Nike, SNKRS, Adidas Confirmed, Palace, Stussy, New Balance, Concepts, Bodega, Undefeated, DSM, A Ma Maniere, Feature, Atmos, Extra Butter, Shoe Palace, BSTN, Union LA, Fear of God, and Travis Scott Shop. This is a roadmap list, **not** a claim that each has an available or authorized API/feed.

### Code example: read-only adapter contract

This is an illustrative boundary, not a working connector. It intentionally has no login, cart, payment, checkout, CAPTCHA solver, stealth, or proxy-rotation methods.

```python
from dataclasses import dataclass
from typing import Protocol, Sequence


@dataclass(frozen=True)
class MonitorQuery:
    keywords: tuple[str, ...] = ()
    product_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class ProductObservation:
    site: str
    product_id: str
    title: str
    url: str
    available: bool
    observed_at: str


class RetailSite(Protocol):
    site_id: str

    async def initialize(self) -> None: ...

    async def discover(
        self, query: MonitorQuery
    ) -> Sequence[ProductObservation]: ...

    async def shutdown(self) -> None: ...
```

Every concrete adapter should declare its source, allowed request budget, data-retention behavior, and failure policy. Unknown or blocked responses should stop or back off; they should not trigger evasive retries.

## 10. Monitoring, checkout, browser, challenge, and proxy recommendations

### Monitoring

- Normalize product observations into a shared model and emit append-only events (`discovered`, `availability_changed`, `source_error`).
- Support product/variant/keyword filters only when the permitted source exposes those fields.
- Deduplicate by `(site, product_id, variant_id, state)` and make event handling idempotent.
- Add bounded polling intervals, conditional requests where supported, jitter only for load distribution within the source's allowed policy, and exponential backoff on errors.
- Do not infer support for shock drops, private feeds, or site maps without explicit authorization.

### Checkout

No shared automated checkout engine is recommended. Retailer purchase flows vary, handle payment data, and can involve access controls. Keep the platform read-only and direct the user to the official product page for checkout. If a business later obtains a retailer-approved purchasing integration, review its contract and security model separately; do not put card data in this application.

### Browser/session

The current monitor uses Selenium only to load and inspect one listing page. Prefer documented feeds/APIs where they are permitted and available. Do not tamper with fingerprints or persist retailer session cookies in a shared worker. Any future browser component should be isolated, resource-limited, observable, and disabled by default.

### CAPTCHA/challenges

There is no current CAPTCHA implementation. For a safe design, detect challenge responses, stop the task, emit a challenge event, and offer a user-directed path to the retailer. Do not build interchangeable CAPTCHA solvers or automatic challenge bypass.

### Proxies

The `proxies` setting is unused. Do not add proxy rotation to bypass restrictions or rate limits. If a legitimate deployment needs network egress controls, use approved corporate egress, document it, and enforce source-specific budgets and circuit breakers.

## 11. Account, profile, storage, analytics, and notifications

### Accounts and profiles

There is no account/session system. Do not expand the current billing JSON into an account vault. Keep account identity outside the monitor where possible; use the retailer's own authentication and checkout flows. If non-payment profile data is required for a permitted integration, define purpose, access control, encryption, retention, and deletion before implementation.

### Storage recommendation

| Store | Recommended use | Avoid |
|---|---|---|
| SQLite | Local single-user prototype: non-sensitive task definitions, source settings, and small discovery history | Card data, CVV, shared multi-worker coordination |
| PostgreSQL | Shared durable tasks, normalized events/results, adapter configuration, migrations, audit trail | Unnecessary secrets or unbounded raw response retention |
| Redis | Ephemeral queue coordination, short-lived dedupe/cache keys, rate-limit counters with TTL | Sole source of truth, long-lived PII/payment storage |

Start with SQLite only for a local read-only prototype; move to PostgreSQL when concurrent workers or shared users are an actual requirement. Add Redis only for a measured queue/cache use case.

### Analytics dashboard

Track task totals and outcomes (started, discovered, failed, timed out, cancelled), source latency/error rates, queue age, dedupe counts, notification delivery, and resource use. If checkout is deliberately outside the service, do not report carts or conversions as platform metrics. Show per-source budgets and stop conditions. Apply retention and access control to event detail.

### Notifications

Define a `NotificationSink` interface and adapters for Discord, Telegram, email, and SMS only after user opt-in and credential storage are designed. Include task/source/status/time and a product URL; never include card data, CVV, session cookies, or full addresses. Use bounded retries, delivery idempotency, and redacted logs.

## 12. Migration plan and priority list

### Phase 0 — contain risk (substantially complete)

1. [x] Removed unattended checkout and payment-data handling from the runtime.
2. [x] Removed anti-detection modifications and proxy configuration.
3. [x] Added validated, safe-default configuration and a dependency manifest. A fully locked dependency set remains outstanding.
4. [x] Ensure browser cleanup with `try/finally`; the remaining browser flow is one-shot and read-only.

### Phase 1 — establish the core

1. Create shared product/query/event models and a typed `RetailSite` protocol.
2. Add a registry that rejects duplicate site IDs and validates adapter capabilities.
3. Implement a fake in-memory adapter and unit tests; do not connect to retailer endpoints yet.
4. Add structured logging, cancellation, bounded execution, and a small error taxonomy.

### Phase 2 — first authorized monitor

1. Select one retailer with a documented, permitted source.
2. Implement read-only discovery, source-specific rate limits, conditional requests, and result deduplication.
3. Add retention controls, integration tests against fixtures, and monitoring metrics.
4. Keep unsupported sites explicitly disabled.

### Phase 3 — operations and expansion

1. Add opt-in notification sinks and a small task UI/CLI.
2. Add PostgreSQL only when shared persistence is needed; Redis only when measured queue/cache load warrants it.
3. Add adapters one at a time after source permissions, data shape, limits, and failure behavior are documented.
4. Review privacy, dependency updates, and operational metrics before each release.

### Priority improvement list

**Completed P0:** removed payment/CVV handling, unattended submission, stealth behavior, and proxy settings; unsupported config is rejected.

**Remaining P1:** dependency lock, package metadata/CI, structured monitoring outcomes, and browser lifecycle tests.

**P2:** adapter contract, authorized-source monitoring engine, source-specific rate limits/deduplication, and health metrics.

**P3:** durable storage, UI, consent-based notifications, and multi-worker scaling—only after an authorized use case and measured need.

## 13. Current scorecard after remediation

Scores assess the repository **after the monitor-only remediation**, not the proposed target. A score of 1 means little or no platform capability is present; 10 requires production-grade design and evidence, not just scaffolding.

| Category | Score | What prevents 10/10 | Steps toward 10 |
|---|---:|---|---|
| Architecture | 2/10 | Checkout responsibilities were removed, but the monitor remains a single-site script without adapter boundaries | Separate monitoring contracts and authorized source adapters; add persistence/UI only when needed |
| Maintainability | 4/10 | Typed config and focused tests exist, but selectors remain hard-coded and there is no package metadata or CI | Add package layout, dependency lock, CI, and adapter contract tests |
| Performance | 3/10 | One-shot page scan avoids retry loops and redundant sleeps, but still launches a browser and has no measurements or cache | Prefer documented feeds where available; measure before tuning; add dedupe/conditional fetch only for authorized sources |
| Scalability | 1/10 | No queue, task isolation, durable state, or worker model | Introduce bounded task execution and durable event/task state only when required |
| Reliability | 4/10 | Config validation and guaranteed cleanup are implemented, but no source integration tests, retry policy, cancellation, or durable state exist | Add deterministic adapter tests, explicit task states, bounded backoff, and operational health checks |
| Security | 6/10 | Payment collection, automatic submission, and stealth behavior are removed; dependency locking and an external integration review remain | Lock and scan dependencies; minimize data; review each authorized source and deployment before adding it |
| Extensibility | 2/10 | The current monitor remains Supreme-specific and has no plugin registry | Adopt an adapter protocol/registry and versioned capability contracts; add authorized adapters individually |
| Modernity | 4/10 | Standard-library typing, tests, and a dependency declaration now exist, but there is no package layout, CI, or observability | Add packaging, CI, structured telemetry, and release process; use async only if measured workload justifies it |

## Audit limitations

This is a complete review of the **tracked repository contents**, which currently consist of one Python source file. There are no hidden services, dependency manifests, external configuration files, deployed runtime, or test suite available here to inspect. No retailer endpoints were contacted; no competitor feature claims were independently checked; no load test, penetration test, or runtime browser test was performed.
