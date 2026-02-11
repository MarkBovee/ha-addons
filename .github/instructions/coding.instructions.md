---
applyTo: '**'
---

# Coding Standards

Project-specific coding standards for this Home Assistant add-ons repository.

---

## Tech Stack

- **Runtime:** Python 3.12+ on Alpine Linux (Docker)
- **Platform:** Home Assistant Supervisor add-ons
- **Key libraries:** `requests`, `paho-mqtt`, `Jinja2`
- **APIs:** Nord Pool, Charge Amps Cloud, SAJ Electric, HA Supervisor REST API

---

## Project Structure

```
ha-addons/
+-- shared/                   # Source of truth for shared modules
+-- battery-api/              # SAJ inverter battery control (prefix: ba_)
+-- battery-manager/          # Battery charge/discharge optimizer (prefix: bm_)
+-- charge-amps-monitor/      # Charge Amps EV charger monitor (prefix: ca_)
+-- energy-prices/            # Nord Pool electricity prices (prefix: ep_)
+-- water-heater-scheduler/   # Price-based water heater control (prefix: wh_)
+-- run_addon.py              # Universal local runner (auto-syncs shared/)
+-- sync_shared.py            # Manual shared module sync
+-- openspec/                 # Specifications and change proposals
```

### Add-on Directory Layout

Each add-on follows this structure:

```
my-addon/
+-- app/
|   +-- __init__.py
|   +-- main.py               # Orchestration, main loop, entity management
|   +-- models.py             # Data models with from_dict/to_dict
|   +-- [name]_api.py         # External API client (requests, auth)
|   +-- [feature].py          # Business logic modules
+-- shared/                   # Copy of root shared/ (synced, never edit directly)
+-- config.yaml               # HA add-on metadata and option schema
+-- Dockerfile                # Alpine-based container build
+-- requirements.txt          # Pinned Python dependencies
+-- run.sh                    # Entrypoint script
+-- README.md                 # Add-on documentation
+-- CHANGELOG.md              # Version history
```

### Shared Modules (`shared/`)

Common utilities shared across all add-ons. **Always edit root `shared/`, never `<addon>/shared/`.**

| Module | Purpose | Key Exports |
|--------|---------|-------------|
| `addon_base.py` | Lifecycle management | `setup_logging()`, `setup_signal_handlers()`, `sleep_with_shutdown_check()`, `run_addon_loop()` |
| `ha_api.py` | HA REST API client | `HomeAssistantApi`, `get_ha_api_config()` |
| `config_loader.py` | Config from JSON/env | `load_addon_config()`, `get_env_with_fallback()`, `get_run_once_mode()` |
| `ha_mqtt_discovery.py` | MQTT Discovery entities | `MqttDiscovery`, `EntityConfig`, `NumberConfig`, `SelectConfig`, `ButtonConfig` |
| `mqtt_setup.py` | MQTT client setup | `setup_mqtt_client()`, `is_mqtt_available()` |

After editing shared modules: run `python sync_shared.py` or use `python run_addon.py` which auto-syncs.

---

## Python Conventions

### Style
- Follow PEP 8
- Use structured log messages: `logger.info("Fetched %s prices", count)`
- Use `setup_logging()` from `shared/addon_base.py`
- Prefer docstrings over inline comments
- Type hints where they add clarity (not strictly enforced)

### Architecture Patterns
- **API clients** in `app/[name]_api.py` - handle auth, requests, response parsing
- **Data models** in `app/models.py` - dataclasses or classes with `from_dict()`/`to_dict()`
- **Business logic** in dedicated modules - keep `main.py` focused on orchestration
- **Reuse `requests.Session`** for connection pooling and auth headers
- **Graceful shutdown**: check `shutdown_event.is_set()` in loops, use `sleep_with_shutdown_check()`

### Main Loop Pattern

```python
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared import (
    setup_logging, setup_signal_handlers, run_addon_loop,
    load_addon_config, get_run_once_mode,
    HomeAssistantApi, get_ha_api_config, setup_mqtt_client,
)

def main():
    logger = setup_logging(name="my-addon")
    shutdown_event = setup_signal_handlers(logger)
    config = load_addon_config(defaults={"interval": 300}, required_fields=["api_key"])
    ha_api = HomeAssistantApi(*get_ha_api_config().values(), logger)
    mqtt = setup_mqtt_client("My Addon", "my_addon", config)
    run_once = get_run_once_mode()

    def update():
        # Fetch data, process, publish entities
        pass

    run_addon_loop(update, config["interval"], shutdown_event, logger, run_once)
```

### Entity Naming
- Prefix with add-on identifier: `ca_`, `ep_`, `bm_`, `ba_`, `wh_`
- Descriptive names: `sensor.ep_price_import`, `sensor.bm_schedule_next_charge`
- Store rich data in entity attributes (price curves, metadata)

### Entity Creation
- **Preferred:** MQTT Discovery via `shared/ha_mqtt_discovery.py` (provides `unique_id`, UI management)
- **Fallback:** REST API via `shared/ha_api.py` (no `unique_id`, entities can't be managed in UI)
- When using REST API: delete old entities on startup, track first run for compact logging

---

## Docker / Dockerfile

```dockerfile
ARG BUILD_FROM=ghcr.io/home-assistant/amd64-base:latest
FROM $BUILD_FROM

RUN apk add --no-cache python3 py3-pip
COPY requirements.txt /tmp/
RUN python3 -m pip install --no-cache-dir --break-system-packages -r /tmp/requirements.txt

COPY shared /app/shared
COPY app /app/app
COPY run.sh /
RUN chmod a+x /run.sh

CMD [ "/run.sh" ]
```

Key rules:
- Always provide `BUILD_FROM` default value
- Use `--break-system-packages` for pip (Alpine PEP 668)
- Copy `shared/` before `app/` for layer caching
- Reference `charge-amps-monitor/Dockerfile` as canonical example

---

## Configuration & Secrets

- `config.yaml`: add-on metadata, options schema, defaults
- `/data/options.json`: runtime config (loaded by `load_addon_config()`)
- `.env` files for local development (never committed)
- `.env.example` to document required variables
- Validate inputs early, fail fast with clear log messages

### Local Development

```bash
python run_addon.py --list                        # List available add-ons
python run_addon.py --addon energy-prices         # Run continuously
python run_addon.py --addon energy-prices --once  # Single iteration
python run_addon.py --addon energy-prices --init-env  # Create .env from template
```

---

## Dependencies

- Pin exact versions in `requirements.txt`
- Keep dependencies minimal (add-ons run on Raspberry Pi)
- Align with Python 3.12+ standard library where possible
