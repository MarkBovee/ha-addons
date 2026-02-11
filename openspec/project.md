# Project Context

## Purpose
Collection of Home Assistant Supervisor add-ons for home energy management. Focus on:
- EV charger monitoring and control (Charge Amps)
- Electricity price optimization (Nord Pool, Dutch market)
- Battery charge/discharge scheduling (SAJ Electric inverters)
- Smart appliance scheduling based on dynamic prices

## Tech Stack
- **Runtime**: Python 3.12+ on Alpine Linux (Docker)
- **Platform**: Home Assistant Supervisor add-ons
- **Libraries**: `requests`, `paho-mqtt`, `Jinja2`
- **APIs**: Nord Pool, Charge Amps Cloud, SAJ Electric, HA Supervisor REST API

## Add-ons

| Add-on | Slug | Entity Prefix | Purpose |
|--------|------|--------------|---------|
| Battery API | battery-api | `ba_` | SAJ inverter battery schedule control |
| Battery Manager | battery-manager | `bm_` | Price/solar/grid-based battery optimization |
| Charge Amps Monitor | charge-amps-monitor | `ca_` | EV charger monitoring and control |
| Energy Prices | energy-prices | `ep_` | Nord Pool prices with import/export calculations |
| Water Heater Scheduler | water-heater-scheduler | `wh_` | Price-based water heater scheduling |

## Architecture

### Add-on Layout
Every add-on follows the same structure:
- `app/main.py` - Orchestration and main loop
- `app/models.py` - Data models
- `app/[name]_api.py` - External API client
- `app/[feature].py` - Business logic
- `shared/` - Copy of root `shared/` (synced for Docker builds)
- `config.yaml` - HA metadata and options schema

### Shared Modules (`shared/`)
Source of truth is root `shared/`. Synced to each add-on via `sync_shared.py`.

| Module | Purpose |
|--------|---------|
| `addon_base.py` | Logging, signal handling, main loop |
| `ha_api.py` | HA REST API client |
| `config_loader.py` | Config from JSON and environment |
| `ha_mqtt_discovery.py` | MQTT Discovery entities with unique_id |
| `mqtt_setup.py` | MQTT client initialization |

### Entity Creation
- Preferred: MQTT Discovery (`ha_mqtt_discovery.py`) - entities have `unique_id`, grouped under devices
- Fallback: REST API (`ha_api.py`) - no `unique_id`, limited UI management

## Domain Context

### Dutch Energy Market
- 15-minute pricing intervals from Nord Pool (96 per day)
- Prices in EUR/MWh, displayed in cents/kWh
- Day-ahead prices published ~13:00 CET
- VAT (21%), grid fees, energy tax applied in calculations

### Conventions
- Entity IDs use add-on prefix: `sensor.ep_price_import`, `sensor.bm_schedule_next_charge`
- Structured logging: `logger.info("Fetched %s prices", count)`
- Graceful shutdown via `shutdown_event.is_set()`
- Configuration via `/data/options.json` (HA Supervisor) or `.env` (local dev)

## Constraints
- No breaking changes to entity names or attribute structures
- Never commit secrets (`.env`, API keys)
- Keep resource usage minimal (Raspberry Pi target)
- Pin exact dependency versions
