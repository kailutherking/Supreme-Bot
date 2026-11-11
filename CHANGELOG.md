# Changelog

Notable project changes are recorded here. Entries summarize repository changes
and do not imply that unimplemented platform features are available.

## Unreleased

### Added

- Added a reusable retail-site registry, query/observation models, monitor
  engine, bounded authorized HTTPS JSON client, and Supreme site adapter.
- Added SQLite product snapshots, observation history, change events, basic
  analytics, and a pending-notification outbox.
- Added opt-in Discord webhook, Telegram, and SMTP email notification sinks.
- Added monitoring, storage, request, and notification integration tests.

### Changed

- Expanded the Supreme scan from `/shop/all/jackets` to `/shop/all/`, preserving
  the local working-tree update.
- Added the local SQLite database path to generated configuration.
- Reworked the README to document the plugin architecture, persistence,
  notification environment variables, and current limitations.

### Not included

- No additional retailer adapter is active; retailer-specific data sources
  require authorization and contract-level review.
- No React UI, authentication, web API, scheduler, PostgreSQL, or Redis service
  has been added.

### Documentation

- The architecture audit and multi-site roadmap are maintained in
  [docs/AUDIT.md](docs/AUDIT.md).

## 2026-11-11 — `1a3c7be`

### Added

- Added validated JSON configuration and restricted-permission default config
  creation.
- Added focused unit tests for configuration validation and listing matching.
- Added a Selenium dependency declaration and a codebase audit/migration report.

### Changed

- Replaced automated checkout with a one-shot, read-only Supreme listing
  monitor that reports matching listing links.
- Simplified matching to require all configured name keywords and a matching
  color, case-insensitively.
- Added browser cleanup in a `finally` block and explicit timeout/error
  outcomes.

### Security

- Removed payment-data handling, cart/checkout/order-submission behavior,
  browser anti-detection modifications, proxy settings, and human-mimic delays.
- Rejects unsupported legacy configuration fields instead of silently
  accepting checkout or credential settings.

### Not included

- No UI, backend API, database, multi-site adapters, continuous scheduler,
  notification integrations, or deployment infrastructure were added.
