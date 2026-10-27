# Lissy Library — Home Assistant Integration

Tracks borrowed items from a Lissy-based public library system.

> **Disclaimer:** This project is an independent, community-developed integration and is not affiliated with, endorsed by, or officially supported by sdt.net AG, BIBLIS, or the LISSY system. All product names and trademarks are the property of their respective owners.

> **Note:** Parts of this code were written and reviewed with the help of AI coding agents (opencode).

## Features

- **Sensors** for each borrowed item (state = due date)
- **Summary sensors**: total borrowed count, next due date
- **Card barcode image** (opt-in): a Code39 barcode of your card number for desk scanning, taken from the portal's displayed Benutzernr. (leading zero included) when available, otherwise the configured username
- **Calendar** entity with all loan deadlines
- **Service** `lissy.renew` to renew items directly from HA

## Installation via HACS

Requires **Home Assistant 2026.9 or newer**.

1. Add this repository as a custom repository in HACS (category: **Integration**)
2. Install **Lissy Library**
3. Restart Home Assistant
4. Go to **Settings → Devices & Services → Add Integration** and search for *Lissy*

## Manual Installation

Copy `custom_components/lissy/` into your HA `config/custom_components/` folder and restart.

## Configuration

During setup you first pick your library, then log in:

| Field | Description |
|---|---|
| Library | Your library, chosen from a dropdown. If it is not listed, select "Enter URL manually" to enter the portal URL yourself — and please [open an issue](https://github.com/jd1/ha-lissy/issues) so the library can be added to the dropdown |
| Lissy URL | URL of your Lissy portal (manual entry only; must end with lissy/lissy.ly) |
| Username | Your library account username |
| Password | Your library account password |

## Options

Open **Settings → Devices & Services → Lissy → Configure**:

| Option | Description |
|---|---|
| Show library card barcode | Off by default. When enabled, an image entity (`image.…_barcode`) is created that renders the number encoded on your library card — the portal's canonical number (leading zeros included) when the portal displays it, otherwise the configured username. Lowercase letters are encoded as uppercase; numbers containing characters outside the Code39 alphabet (A-Z, 0-9, space, `- . $ / + %`) are rejected and the entity is not created. |

## Services

### `lissy.renew`

Renews borrowed items.

| Target | Effect |
|---|---|
| Lissy device | Renews all loans for that account |
| Item sensor entity | Renews that specific item only |

## Automatic renewal

Import the blueprint
[![Open your Home Assistant instance and show the blueprint import dialog with a specific blueprint pre-filled.](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fraw.githubusercontent.com%2Fjd1%2Fha-lissy%2Frefs%2Fheads%2Fmain%2Fblueprints%2Fautomation%2Flissy_auto_renew.yaml)

or copy `blueprints/automation/lissy_auto_renew.yaml` from this repository into your HA `config/blueprints/automation/` folder.

Go to **Settings → Automations → Blueprints** and create an automation from **Lissy — Auto-renew loans**.

The blueprint runs daily at a configurable time and calls `lissy.renew` only when at least one item is due within the configured number of days (default: 3). It uses the `days_until_due` attribute exposed by each item sensor.

## Development

A Docker Compose setup is included for local testing:

```bash
./scripts/start-ha.sh
```

Opens Home Assistant at http://localhost:8123 with the integration mounted read-only from `custom_components/`.
The start script pulls the latest `:stable` image first, so each run tests against the current Home Assistant release.
Changes to source files take effect after restarting the HA container (`docker compose restart homeassistant`).

To inspect what the scraper actually sees (label variants, table quirks, the Benutzernr. placement), run `uv run scripts/dump-portal.py` — it performs the same read-only login + loans fetch and saves every page under `portal-dump/`. It needs no Home Assistant installation and never touches the renew flow.
