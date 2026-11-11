# Changelog

Notable project changes are recorded here. Entries summarize repository changes
and do not imply that unimplemented platform features are available.

## Unreleased

### Documentation

- Added project setup, configuration, usage, environment, deployment, and
  limitation details to the README.
- Added this changelog to track shipped changes.

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
