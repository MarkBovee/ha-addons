# Project Context

## Purpose
Collection of Home Assistant Supervisor add-ons for home automation and energy management. Focus on:
- EV charger monitoring and control
- Energy price optimization
- Smart appliance scheduling based on dynamic electricity prices
- Integration with Dutch energy market (Nord Pool)

## Tech Stack
- **Runtime**: Python 3.12+
- **Platform**: Home Assistant Supervisor add-ons (Docker-based)
- **Core Libraries**: 
  - `requests` for HTTP/API calls
  - `Jinja2` for template processing
  - Standard library (`logging`, `signal`, `threading`, `json`)
- **API Integrations**:
  - Charge Amps Cloud API (EV chargers)
  - Nord Pool Day-Ahead Prices API (electricity prices)
  - Home Assistant Supervisor REST API (entity management)

## Project Conventions

### Code Style
- **Python**: Follow PEP 8 conventions with descriptive variable names
- **Logging**: Use structured logging with `logger.info("Message with %s", variable)` format
- **Docstrings**: Module, class, and function docstrings required; prefer docstrings over inline comments
- **Error Handling**: Fail fast with clear error messages; log exceptions with context
- **Type Hints**: Use where beneficial for clarity (not strictly enforced)

### Architecture Patterns
- **Separation of Concerns**:
  - `app/[api_name]_api.py` - External API clients (requests, auth, parsing)
  - `app/models.py` - Data models (from_dict/to_dict methods)
  - `app/[feature]_processor.py` - Business logic (calculations, transformations)
  - `app/main.py` - Orchestration (main loop, signal handlers, HA entity management)
- **Session Management**: Reuse `requests.Session` objects for connection pooling and auth headers
- **Configuration**: YAML-based (`config.yaml`) with schema validation, externalized from code
- **Graceful Shutdown**: Honor `shutdown_flag` and SIGTERM/SIGINT signals in long-running loops
- **Entity Management**: Create-or-update pattern (check existence, create if missing, update otherwise)

### Testing Strategy
- Local testing scripts (`run_local.py`, `run_local.ps1`, `run_local.sh`) using `.env` files
- Manual validation in Home Assistant dev instances
- Unit tests planned but not yet implemented

### Git Workflow
- **Branching Strategy**:
  - `master` branch for stable releases
  - `feature/[change-id]` for new features (with OpenSpec change folders)
  - `fix/[descriptive-name]` for bug fixes
  - `refactor/[descriptive-name]` for code improvements
  - `docs/[descriptive-name]` for documentation updates
- **Commit Style**: `feat(scope): description` / `fix(scope): description` / `docs(scope): description`
- **OpenSpec Workflow**: Feature changes require proposal in `openspec/changes/[number]-[change-id]/`

## Domain Context

### Home Assistant Add-ons
- Add-ons run as Docker containers managed by Home Assistant Supervisor
- `config.yaml` defines metadata, supported architectures, options schema
- `Dockerfile` builds container (typically FROM Python base image)
- `run.sh` is entrypoint script that executes Python app
- Add-ons communicate with HA via Supervisor REST API (`/api/states/`, `/api/services/`)

### Dutch Energy Market
- 15-minute pricing intervals (96 per day) from Nord Pool
- Prices in EUR/MWh, converted to cents/kWh for user display
- Day-ahead prices published ~13:00 CET for next day
- Need to handle VAT (21%), grid fees, energy tax in price calculations
- CET timezone important for aligning prices with local time

### Entity Naming Conventions
- Prefix entities with add-on identifier (e.g., `ca_` for Charge Amps, `ep_` for Energy Prices)
- Use descriptive names: `sensor.ep_price_import`, `sensor.ep_price_export`
- Store rich data in entity attributes (price curves, percentiles, metadata)

## Important Constraints
- **No Breaking Changes**: Avoid breaking existing entity names or attribute structures
- **Secrets Management**: Never commit credentials; use `.env` for local testing, config UI for production
- **Resource Limits**: Add-ons run on Raspberry Pi devices; keep memory/CPU usage minimal
- **Dependencies**: Pin exact versions in `requirements.txt` to prevent breakage
- **Documentation**: Update README and repository.json whenever adding/changing add-ons

## External Dependencies

### APIs
- **Charge Amps Cloud API**: `https://my.charge.space/api/` (authentication via JWT)
- **Nord Pool Day-Ahead API**: `https://dataportal-api.nordpoolgroup.com/api/DayAheadPrices` (no auth required)
- **Home Assistant Supervisor API**: `http://supervisor/core/api/` (requires `homeassistant_api: true` in config.yaml)

### Services
- Home Assistant Supervisor (container orchestration, config management, API proxy)
- Docker (container runtime)
