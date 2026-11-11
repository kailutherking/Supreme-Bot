# Supreme Listing Monitor

A one-shot, read-only monitor for matching product listings on Supreme's jackets
page. It reports matching listing URLs so you can open the retailer's site and
manually verify availability and variant.

This project does **not** add items to carts, log in, store payment details,
submit orders, solve challenges, or rotate proxies. It is not a multi-site
platform or a continuously running restock service.

## Requirements

- Python 3.10 or newer
- Google Chrome installed locally
- Network access to the configured Supreme shop page

Selenium Manager, included with Selenium, manages the browser driver. No
separate `webdriver-manager` installation is used.

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

On Windows, activate the virtual environment with
`.venv\Scripts\activate` before installing the requirements.

## Configure

Run the program once:

```bash
python supremebot.py
```

If `config.json` does not exist in the current working directory, the program
creates it with safe defaults and exits. The generated file is restricted to
the current user on POSIX systems. Add one or more targets, for example:

```json
{
  "target_items": [
    {
      "keywords": ["Faux", "Jacket"],
      "color": "Red"
    }
  ],
  "settings": {
    "headless": false
  }
}
```

Every keyword must appear in the listing name, and the configured color must
appear in the listing color, case-insensitively. The monitor does not inspect
or select sizes and does not guarantee that an item is still available when
you open it.

Supported configuration fields:

| Field | Type | Description |
|---|---|---|
| `target_items` | array | Product-name keywords and color to match. May be empty, but the monitor will report that no targets are configured. |
| `target_items[].keywords` | non-empty array of strings | All words must be present in a listing name. |
| `target_items[].color` | non-empty string | Must be present in the listing color. |
| `settings.headless` | boolean | Run Chrome without a visible window when `true`. |

Legacy billing, payment, checkout, proxy, and other unsupported fields are
rejected. Remove them rather than copying sensitive information into the
configuration.

## Run

After editing `config.json`, run:

```bash
python supremebot.py
```

Each invocation loads the Supreme jackets listing once, looks for matches, and
exits. Matching URLs are printed to the console. Open the retailer page
yourself to confirm the product and complete any desired actions there.

Exit codes:

- `0`: scan completed (whether or not a match was found), or safe config
  defaults were created.
- `1`: the shop page or product listings timed out.
- `2`: invalid configuration, no targets configured, or Selenium unavailable.

## Environment variables

The application does not read environment variables. Configuration is read
from `config.json` in the current working directory.

## Tests

Run the unit tests with:

```bash
python -m unittest discover -s tests -v
```

## Deployment and limitations

This is a local, one-shot CLI tool—not a hosted service, daemon, or production
multi-site platform. There is no scheduler, API, database, dashboard,
notification integration, deployment configuration, or retailer adapter beyond
the hard-coded Supreme listing page. No retailer interaction was validated as
part of the source-level audit. Respect the retailer's terms and access
policies; do not use this tool to bypass access controls or site protections.

See [docs/AUDIT.md](docs/AUDIT.md) for the architecture audit, security
assessment, migration plan, and remaining work.
