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

Renews one or more borrowed items.

| Parameter | Description |
|---|---|
| `entity_id` | One or more item sensor entities to renew |