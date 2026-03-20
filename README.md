# Local Timezone for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)

A Home Assistant custom integration that determines your IANA timezone from GPS coordinates using **pure Python** — no external API calls required.

Built for RVers, van lifers, and anyone whose home moves.

## Features

- **Offline timezone lookup** — uses [timezonefinder](https://github.com/jannikmi/timezonefinder) for local computation
- **Four sensors:**
  - `sensor.local_timezone` — IANA timezone string (e.g., `America/Denver`)
  - `sensor.local_timezone_abbreviation` — Current abbreviation (e.g., `MDT`, `MST`)
  - `sensor.local_timezone_utc_offset` — UTC offset (e.g., `UTC-6`)
  - `sensor.local_timezone_dst_active` — Whether DST is currently active (`on`/`off`)
- **Automatic updates** — sensors update whenever your GPS coordinates change
- **Config flow UI** — set up entirely from the Home Assistant UI
- **No external dependencies** — works offline, no API keys needed

## Installation

### HACS (Recommended)

1. Open HACS in Home Assistant
2. Click the three dots → **Custom repositories**
3. Add `https://github.com/manos/hass-local-timezone` as an **Integration**
4. Search for "Local Timezone" and install
5. Restart Home Assistant

### Manual

1. Copy the `custom_components/local_timezone` folder to your `config/custom_components/` directory
2. Restart Home Assistant

## Configuration

1. Go to **Settings → Devices & Services → Add Integration**
2. Search for **"Local Timezone"**
3. Select your latitude and longitude sensor entities
4. Done!

The integration will create four sensors that automatically update when your GPS coordinates change.

## Use Cases

### Automatic System Timezone Updates

Use with a shell command to keep your host system timezone in sync:

```yaml
shell_command:
  update_timezone: "timedatectl set-timezone {{ states('sensor.local_timezone') }}"

automation:
  - alias: "Update system timezone"
    trigger:
      - platform: state
        entity_id: sensor.local_timezone
    action:
      - service: shell_command.update_timezone
```

### Dashboard Display

Show your current timezone info on a dashboard card with the timezone, abbreviation, UTC offset, and DST status.

## Requirements

- Home Assistant 2024.1 or newer
- GPS latitude/longitude sensor entities (e.g., from Victron GX, Peplink, phone tracker, etc.)

## Credits

- [timezonefinder](https://github.com/jannikmi/timezonefinder) by Jannik Michelfeit — the pure Python timezone lookup engine
- Inspired by [hass-geolocator](https://github.com/SmartyVan/hass-geolocator) (which uses external APIs)
