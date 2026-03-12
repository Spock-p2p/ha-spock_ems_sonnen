# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Home Assistant custom integration that bridges **sonnenBatterie** devices with the **Spock P2P** energy management platform. Every 60 seconds it: reads telemetry from the Sonnen local REST API, posts it to Spock cloud, receives an operation command, and applies it back to the battery.

Domain: `spock_ems_sonnen` | HACS-compatible | Requires HA >= 2024.6.0

## Architecture

The integration follows the standard HA custom component pattern with a central `DataUpdateCoordinator`:

- **`__init__.py`** — `SpockEnergyCoordinator` orchestrates the 60s cycle: Sonnen GET `/api/v2/status` → normalize telemetry → POST to Spock API → apply returned command (charge/discharge/auto/none) back to Sonnen via PUT/POST.
- **`config_flow.py`** — Setup + options flow. Validates Spock API token, Sonnen IP reachability, and Sonnen Auth Token during configuration. All 4 parameters are reconfigurable via options without recreating the entry.
- **`sensor.py`** — Two sensor groups: `TELEMETRY_SENSORS` (7 sensors from battery data) and `SPOCK_SENSORS` (2 sensors from cloud response). Both use `CoordinatorEntity`.
- **`switch.py`** — Single `SpockPollingSwitch` that enables/disables the coordinator cycle via `hass.data[DOMAIN][entry_id]["is_enabled"]`.
- **`const.py`** — All configuration keys, API endpoint URL, platform list, scan interval.

## Key Data Flow Details

- **Sign convention**: Sonnen's `GridFeedIn_W` sign is **inverted** when mapping to Spock's `ongrid_power` (Sonnen: +export; Spock: +import).
- **Battery capacity**: Calculated as `RemainingCapacity_Wh / (RSOC / 100)`.
- **SOC**: Uses `USOC` (user-visible), falls back to `RSOC`.
- **Command deduplication**: `_last_cmd_fingerprint` tracks last applied command.
- **Operating modes sent to Sonnen**: `EM_OperatingMode=1` (Manual) for charge/discharge, `EM_OperatingMode=2` (Self-Consumption) for auto.

## APIs

- **Sonnen local** (no auth for reads, `Auth-Token` header for writes): `http://{IP}/api/v2/`
- **Spock cloud** (`X-Auth-Token` header): `https://ems-ha.spock.es/api/ems_sonnen`

## Configuration Parameters

`api_token` (Spock), `plant_id` (Spock), `sonnen_ip` (battery LAN IP), `sonnen_token` (battery Auth-Token)

## Development Notes

- No build system or test suite — this is a pure Python HA integration installed via HACS or manual copy into `custom_components/`.
- All async HTTP uses `homeassistant.helpers.aiohttp_client.async_get_clientsession`.
- Translations in `translations/en.json` and `translations/es.json` — project is bilingual (code comments in Spanish, UI in both).
- Debug logging: set `custom_components.spock_ems_sonnen: debug` in HA's `configuration.yaml` logger section.
