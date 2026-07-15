# Lissy Library — Home Assistant Integration

Tracks borrowed items from a Lissy-based public library system.

> **Disclaimer:** This project is an independent, community-developed integration and is not affiliated with, endorsed by, or officially supported by sdt.net AG, BIBLIS, or the LISSY system. All product names and trademarks are the property of their respective owners.

## Features

- **Sensors** for each borrowed item (state = due date)
- **Summary sensors**: total borrowed count, next due date
- **Calendar** entity with all loan deadlines
- **Service** `lissy.renew` to renew items directly from HA

## Installation via HACS

1. Add this repository as a custom repository in HACS (category: **Integration**)
2. Install **Lissy Library**
3. Restart Home Assistant
4. Go to **Settings → Devices & Services → Add Integration** and search for *Lissy*

## Manual Installation

Copy `custom_components/lissy/` into your HA `config/custom_components/` folder and restart.

## Configuration

During setup you will be asked for:

| Field | Description |
|---|---|
| Username | Your library account username |
| Password | Your library account password |
| Base URL | URL of your Lissy portal (optional if using the default) |

## Services

### `lissy.renew`

Renews borrowed items.

| Target | Effect |
|---|---|
| Lissy device | Renews all loans for that account |
| Item sensor entity | Renews that specific item only |

## Automatic renewal

Copy `blueprints/automation/lissy_auto_renew.yaml` from this repository into your HA `config/blueprints/automation/` folder, then go to **Settings → Automations → Blueprints** and create an automation from **Lissy — Auto-renew loans**.

The blueprint runs daily at a configurable time and calls `lissy.renew` only when at least one item is due within the configured number of days (default: 3). It uses the `days_until_due` attribute exposed by each item sensor.

## Development

A Docker Compose setup is included for local testing:

```bash
./scripts/start-ha.sh
```

Opens Home Assistant at http://localhost:8123 with the integration mounted read-only from `custom_components/`.
Changes to source files take effect after restarting the HA container (`docker compose restart homeassistant`).