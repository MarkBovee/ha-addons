<!-- OPENSPEC:START -->
# OpenSpec Instructions

These instructions are for AI assistants working in this project.

Always open `@/openspec/AGENTS.md` when the request:
- Mentions planning or proposals (words like proposal, spec, change, plan)
- Introduces new capabilities, breaking changes, architecture shifts, or big performance/security work
- Sounds ambiguous and you need the authoritative spec before coding

Use `@/openspec/AGENTS.md` to learn:
- How to create and apply change proposals
- Spec format and conventions
- Project structure and guidelines

Keep this managed block so 'openspec update' can refresh the instructions.

<!-- OPENSPEC:END -->

# AI Agent Guidelines

Use this document whenever you plan, review, or implement changes in this repository. It captures the conventions we already follow plus industry guidance on `agents.md` structure, PR hygiene, and documentation style drawn from the [agentsmd.io best practices](https://agentsmd.io/agents-md-best-practices?utm_source=openai).

---

## Repository Overview

- `charge-amps-monitor/` – Home Assistant add-on written in Python; talks to the Charge Amps cloud via the `ChargerApi` client (`app/charger_api.py`) and pushes entities into Home Assistant through REST calls in `app/main.py`.
- `energy-prices/` – Home Assistant add-on for fetching Nord Pool electricity prices and calculating import/export costs.
- `shared/` – **Shared Python modules** used by all add-ons (see [Shared Modules Architecture](#shared-modules-architecture) below).
- `repository.json`, root `README.md`, and per-addon `README.md` files describe how Home Assistant discovers and installs each add-on. Keep them accurate whenever you add or rename files.
- Future add-ons should live in peer directories, each with its own `app/`, `config.yaml`, and docs. Add nested `agents.md` files inside each addon if they require rules that differ from the items below (hierarchical `agents.md` files keep guidance scoped as the repo grows).

---

## Coding Standards

### Python add-ons

1. **Target runtime**: Python 3.12+. Align new dependencies with `requirements.txt` and pin exact versions.
2. **Structure**: Place networking/API logic in dedicated modules (e.g., `app/charger_api.py`, `app/nordpool_api.py`) and Home Assistant orchestration in `app/main.py`.
3. **Logging**: Use `setup_logging()` from `shared/addon_base.py` and prefer structured messages (`logger.info("Fetched %s charge points", count)`).
4. **HTTP**: Reuse the existing `requests.Session` pattern so authentication headers and retries stay centralized.
5. **Models**: Extend or add data models in `app/models.py` instead of passing bare dicts around.
6. **Graceful shutdowns**: Use `setup_signal_handlers()` from `shared/addon_base.py` which returns a `threading.Event`. Long-running loops must check `shutdown_event.is_set()` each iteration.
7. **Use shared modules**: Import common functionality from `shared/` instead of duplicating code. See [Shared Modules Architecture](#shared-modules-architecture).

### Commenting & documentation

- Python: keep module, function, and class docstrings concise and actionable. Prefer doctrings over inline comments unless clarifying tricky logic.
- .NET or C# utilities (if/when added): use XML documentation comments that include `summary`, `param`, `returns`, and `exception` tags, e.g.:

  ```csharp
  /// <summary>
  /// Describe the side effect or value returned.
  /// </summary>
  /// <param name="cancellationToken">How cancellation propagates.</param>
  /// <returns>The processed payload.</returns>
  public Task<ChargerResult> ProcessAsync(CancellationToken cancellationToken) { ... }
  ```

- Keep comments accurate—update them whenever code changes. Avoid restating what the code already makes obvious.

### YAML & metadata

- Ensure `config.yaml` values match add-on reality (name, slug, version, supported architectures).
- When you add new configuration options, document both the `options` defaults and the `schema` types, then reference them in the add-on README.

### Docker / Dockerfile

All add-ons run in Docker containers built from Alpine-based Home Assistant images. Follow these patterns:

1. **BUILD_FROM argument**: Always provide a default value so the Dockerfile works standalone:
   ```dockerfile
   ARG BUILD_FROM=ghcr.io/home-assistant/amd64-base:latest
   FROM $BUILD_FROM
   ```

2. **Python pip installs**: Alpine 3.22+ enforces PEP 668 (externally-managed Python). Use `--break-system-packages` to install pip packages:
   ```dockerfile
   RUN python3 -m pip install --no-cache-dir --break-system-packages -r requirements.txt
   ```

3. **run.sh location**: Copy `run.sh` to the root (`/run.sh`) and reference it absolutely:
   ```dockerfile
   COPY run.sh /
   RUN chmod a+x /run.sh
   CMD [ "/run.sh" ]
   ```

4. **Minimal layers**: Combine related commands where practical, but keep the `requirements.txt` copy separate for Docker layer caching.

5. **Reference implementation**: Use `charge-amps-monitor/Dockerfile` as the canonical pattern for new add-ons.

6. **Shared modules**: Copy the `shared/` folder into each add-on directory (see [Shared Modules Architecture](#shared-modules-architecture)):
   ```dockerfile
   COPY shared /app/shared
   COPY app /app/app
   ```

---

## Shared Modules Architecture

This repository uses a **shared module pattern** to avoid code duplication across add-ons. Common utilities live in `shared/` at the repository root and are copied to each add-on.

### Why Three `shared/` Folders?

Home Assistant add-ons build inside Docker containers with access **only to files within the add-on's directory**. The Docker build context cannot reach parent directories.

```
ha-addons/
├── shared/                      # ← SOURCE OF TRUTH (edit here)
├── charge-amps-monitor/
│   └── shared/                  # ← COPY (for Docker build)
└── energy-prices/
    └── shared/                  # ← COPY (for Docker build)
```

### Available Shared Modules

| Module | Purpose | Key Exports |
|--------|---------|-------------|
| `addon_base.py` | Add-on lifecycle | `setup_logging()`, `setup_signal_handlers()`, `sleep_with_shutdown_check()`, `run_addon_loop()` |
| `ha_api.py` | HA REST API client | `HomeAssistantApi`, `get_ha_api_config()` |
| `config_loader.py` | Configuration loading | `load_addon_config()`, `get_env_with_fallback()`, `get_run_once_mode()` |
| `mqtt_setup.py` | MQTT Discovery | `setup_mqtt_client()`, `is_mqtt_available()`, `get_entity_config_class()` |

### Keeping Shared Modules in Sync

**Always edit `shared/` at the repository root**, then sync to add-ons:

```bash
# Manual sync
python sync_shared.py

# Auto-sync when running locally (recommended)
python run_addon.py --addon energy-prices  # syncs automatically
```

### Creating a New Add-on with Shared Modules

1. **Create the add-on directory structure:**
   ```
   my-new-addon/
   ├── app/
   │   ├── __init__.py
   │   └── main.py
   ├── shared/              # Will be synced
   ├── config.yaml
   ├── Dockerfile
   ├── requirements.txt
   ├── run.sh
   └── README.md
   ```

2. **Copy shared folder:**
   ```bash
   python sync_shared.py
   ```

3. **Import from shared in your `app/main.py`:**
   ```python
   import sys
   import os
   sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
   
   from shared import (
       setup_logging,
       setup_signal_handlers,
       sleep_with_shutdown_check,
       HomeAssistantApi,
       get_ha_api_config,
       load_addon_config,
       get_run_once_mode,
       setup_mqtt_client,
   )
   ```

4. **Use shared utilities in your main function:**
   ```python
   def main():
       logger = setup_logging("my-new-addon")
       shutdown_event = setup_signal_handlers(logger)
       
       config = load_addon_config(
           config_path="/data/options.json",
           defaults={"update_interval": 300},
           required_fields=["api_key"]
       )
       
       ha_config = get_ha_api_config()
       ha_api = HomeAssistantApi(ha_config["url"], ha_config["token"], logger)
       
       run_once = get_run_once_mode()
       
       while not shutdown_event.is_set():
           # Your add-on logic here
           if run_once:
               break
           sleep_with_shutdown_check(shutdown_event, config["update_interval"], logger)
   ```

5. **Commit all three locations:**
   ```bash
   git add shared/ my-new-addon/shared/
   git commit -m "feat(my-new-addon): add new addon with shared modules"
   ```

### Important Rules

- **NEVER edit `<addon>/shared/` directly** – always edit `shared/` at the root
- **Run `sync_shared.py`** after any changes to shared modules
- **Commit all copies** – the add-on folders need their own copy for Docker builds
- **`run_addon.py` auto-syncs** – use it for local development to avoid sync issues

---

## API & Home Assistant Integration

1. `ChargerApi.authenticate()` posts to `https://my.charge.space/api/auth/login` and stores the JWT token plus expiration buffer. Always call `_ensure_authenticated()` before issuing new API requests.
2. `ChargerApi.get_charge_points()` posts to `/api/users/chargepoints/owned?expand=ocppConfig`. Parse responses into `ChargePoint` / `Connector` model instances via their `from_dict` helpers instead of reimplementing parsing.
3. Entity management happens through Home Assistant's Supervisor REST API via the `HomeAssistantApi` class in `shared/ha_api.py`:
   - `ha_api.create_or_update_entity()` issues authenticated POSTs to `/api/states/{entity_id}`.
   - `ha_api.delete_entity()` removes stale IDs before recreating them.
   - `ha_api.delete_entities()` batch-deletes a list of old entity IDs (use for cleanup on startup).
4. Whenever you add new Home Assistant entities, ensure friendly names, units, icons, and prefixes follow the existing `ca_` or `ep_` conventions so dashboards remain consistent.

### Entity Creation Best Practices

The REST API `/api/states/` approach has a known limitation: entities created this way do **not** have a `unique_id`, so they cannot be managed from the HA UI (you'll see a warning about this). This is by design - the REST API is meant for simple state updates, not full entity registration.

**Why unique_id matters:**
- Without `unique_id`, entities cannot be renamed, hidden, or managed in the HA UI
- Entities will show a warning in the entity settings
- Entity settings are not persisted across restarts

**Current workaround (REST API):**

To mitigate issues with the REST API approach:

1. **Delete old entities on startup**: Call `delete_old_entities()` at startup to remove any stale entities before recreating them. This ensures a clean state.

2. **Track first run**: Only log entity creation details once (first run), then use compact logging for subsequent updates:
   ```python
   first_run = True
   while not shutdown_flag:
       update_ha_entities(data, first_run=first_run)
       first_run = False
   ```

3. **Use consistent naming**: Entity IDs should use a prefix unique to your add-on:
   - `ca_` for charge-amps-monitor (e.g., `sensor.ca_charger_power_kw`)
   - `ep_` for energy-prices (e.g., `sensor.ep_price_import`)

4. **Maintain old_entities list**: When renaming entities, add the old names to the `delete_old_entities()` list so they get cleaned up.

**Future improvement: MQTT Discovery**

For proper `unique_id` support, migrate to MQTT Discovery. This requires:
- Mosquitto MQTT broker add-on installed in Home Assistant
- `paho-mqtt` Python dependency
- Publishing discovery payloads to `homeassistant/sensor/<object_id>/config`
- Publishing state updates to dedicated state topics

Example MQTT discovery payload for a sensor with unique_id:
```json
{
  "name": "Electricity Import Price",
  "unique_id": "ep_price_import",
  "state_topic": "energy-prices/sensor/price_import/state",
  "unit_of_measurement": "cents/kWh",
  "device_class": "monetary",
  "device": {
    "identifiers": ["energy_prices_addon"],
    "name": "Energy Prices",
    "manufacturer": "HA Addons",
    "model": "Nord Pool Price Monitor"
  }
}
```

This approach creates entities that:
- Have proper `unique_id` for UI management
- Are grouped under a device in the HA UI
- Persist settings across restarts
- Can be renamed/hidden by users

---

## Configuration, Secrets, and Local Debugging

- Local scripts (`run_local.py`, `run_local.ps1`, `run_local.sh`) expect a `.env` file with Charge Amps and Home Assistant credentials. Never commit `.env` or other secrets; rely on `.env.example` when documenting new variables.
- Environment variables should fall back to safe defaults (`HA_API_URL`, `HA_API_TOKEN`, etc.) like in `get_ha_api_url()` and `get_ha_api_token()`. Mirror that pattern for new settings.
- Validate inputs early (e.g., ensure intervals are positive integers) and fail fast with clear log messages.

### Using run_addon.py (Universal Add-on Runner)

The `run_addon.py` script at the repository root is the **preferred way to run and test add-ons locally**:

```bash
# List all available add-ons
python run_addon.py --list

# Run an add-on (continuous mode)
python run_addon.py --addon energy-prices

# Run a single iteration then exit (for testing)
python run_addon.py --addon energy-prices --once

# Initialize .env from .env.example
python run_addon.py --addon energy-prices --init-env

# Dry run (show config without executing)
python run_addon.py --addon energy-prices --dry-run
```

**Key features:**
- Loads `.env` files automatically (root `.env` → addon `.env`)
- `--once` flag sets `RUN_ONCE=1` env var to exit after one iteration
- Validates required environment variables per add-on
- Normalizes token env vars (`SUPERVISOR_TOKEN` ↔ `HA_API_TOKEN`)

**Add-ons should support `RUN_ONCE` mode:**
```python
run_once = os.getenv('RUN_ONCE', '').lower() in ('1', 'true', 'yes')
if run_once:
    logger.info("Running single iteration (RUN_ONCE mode)")
    # ... do work ...
    break  # Exit after first iteration
```

---

## Workflow Expectations

### Bundling changes

- Keep pull requests scoped: group related edits (e.g., API change + entity update) in the same PR, but avoid mixing unrelated add-ons or refactors.
- Update every artifact affected by the change—code, `README.md`, `CHANGELOG.md`, and `config.yaml`—in one bundle so reviewers see the full context.

### Commit / PR checklist

- `feat(scope): short explanation` commit style keeps history legible.
- Before opening a PR:
  - Run local tests or scripts (`python run_local.py`) with representative credentials.
  - Lint or format Python files (e.g., `ruff`, `black`) if you introduce new code.
  - Verify Home Assistant entity creation end-to-end in a dev instance when possible.
  - Confirm documentation and sample configs match the new behavior.
  - Remove leftover debug prints and commented-out code.

### Reviews & automation

- Provide concrete examples in the PR description: highlight files to follow when adding new sensors (`app/main.py` entity helpers, `app/models.py` parsing logic).
- Mention any new environment variables or secrets clearly so deployers can update their setups.

---

## Extending This Document

- Add directory-specific `agents.md` files whenever an add-on needs custom rules. Reference this root document from those files for shared rules.
- As new languages enter the repo, append language-specific sections (Go, TypeScript, etc.) including their lint/test workflows and documentation standards.

Following these guardrails keeps AI agents and humans aligned, ensures clean documentation (including XML comments where applicable), and helps us ship tightly scoped, well-tested Home Assistant add-ons.***

