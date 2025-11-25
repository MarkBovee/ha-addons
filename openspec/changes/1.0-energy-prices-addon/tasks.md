# Energy Prices Add-on - Implementation Tasks

**Change ID:** 1.0-energy-prices-addon  
**Version:** 1.0  
**Status:** 🟡 **IN PROGRESS - 17% COMPLETE**

---

## Phase 1: Add-on Structure & Configuration ✅

**Target:** 0% → 17% | **Status:** COMPLETE

- [x] 1.1 Create `energy-prices/` directory structure - **DONE [16:35]**
  - [x] 1.1.1 Create `energy-prices/app/` directory
  - [x] 1.1.2 Create `energy-prices/app/__init__.py`
  - [x] 1.1.3 Create placeholder files for API, models, processor, main

- [x] 1.2 Create `config.yaml` with add-on metadata - **DONE [16:35]**
  - [x] 1.2.1 Define name, description, version, slug
  - [x] 1.2.2 Set `homeassistant_api: true` for entity management
  - [x] 1.2.3 Define supported architectures (aarch64, amd64, armhf, armv7, i386)

- [x] 1.3 Define configuration options schema - **DONE [16:35]**
  - [x] 1.3.1 Add `delivery_area` (string, default: "NL")
  - [x] 1.3.2 Add `currency` (string, default: "EUR")
  - [x] 1.3.3 Add `timezone` (string, default: "CET")
  - [x] 1.3.4 Add `import_price_template` (string, required)
  - [x] 1.3.5 Add `export_price_template` (string, required)
  - [x] 1.3.6 Add `fetch_interval_minutes` (int, default: 60)

- [x] 1.4 Create `Dockerfile` - **DONE [16:35]**
  - [x] 1.4.1 Use Python 3.12+ base image
  - [x] 1.4.2 Copy app files to container
  - [x] 1.4.3 Install dependencies from requirements.txt
  - [x] 1.4.4 Set entrypoint to run.sh

- [x] 1.5 Create `run.sh` entrypoint script - **DONE [16:35]**
  - [x] 1.5.1 Add shebang and error handling
  - [x] 1.5.2 Execute Python app/main.py with logging

- [x] 1.6 Create `requirements.txt` - **DONE [16:35]**
  - [x] 1.6.1 Add `requests>=2.31.0`
  - [x] 1.6.2 Add `Jinja2>=3.1.0`

- [x] 1.7 Create `README.md` with basic structure - **DONE [16:35]**
  - [x] 1.7.1 Add overview section
  - [x] 1.7.2 Add installation instructions placeholder
  - [x] 1.7.3 Add configuration section placeholder

**Phase 1 Completion Criteria:**
- Directory structure matches charge-amps-monitor pattern
- config.yaml has valid schema with all required fields
- Dockerfile builds successfully (empty app is OK)
- README has basic sections outlined

---

## Phase 2: Nord Pool API Client ⏳

**Target:** 17% → 33%

- [ ] 2.1 Create `app/models.py` with data models
  - [ ] 2.1.1 Define `PriceInterval` class with `start_time`, `end_time`, `price_cents_kwh` fields
  - [ ] 2.1.2 Add `from_dict()` classmethod for JSON parsing
  - [ ] 2.1.3 Add `to_dict()` method for serialization
  - [ ] 2.1.4 Add `__repr__()` for debugging

- [ ] 2.2 Create `app/nordpool_api.py` with API client
  - [ ] 2.2.1 Create `NordPoolApi` class with constructor
  - [ ] 2.2.2 Add `BASE_URL` constant: `https://dataportal-api.nordpoolgroup.com/api/DayAheadPrices`
  - [ ] 2.2.3 Initialize `requests.Session()` for connection pooling

- [ ] 2.3 Implement `fetch_prices()` method
  - [ ] 2.3.1 Accept `date` (YYYY-MM-DD), `delivery_area`, `currency` parameters
  - [ ] 2.3.2 Build query string with parameters
  - [ ] 2.3.3 Set required headers (Accept, Origin, Referer for CORS)
  - [ ] 2.3.4 Make GET request with timeout (30s)

- [ ] 2.4 Handle API responses
  - [ ] 2.4.1 Handle HTTP 200: parse JSON, extract `multiAreaEntries`
  - [ ] 2.4.2 Handle HTTP 204: return empty list (data not available)
  - [ ] 2.4.3 Handle HTTP errors: log and raise with context
  - [ ] 2.4.4 Handle network errors: log and raise with retry suggestion

- [ ] 2.5 Parse price data
  - [ ] 2.5.1 Iterate through `multiAreaEntries` array
  - [ ] 2.5.2 Extract `deliveryStart`, `deliveryEnd` (UTC ISO 8601 strings)
  - [ ] 2.5.3 Extract `entryPerArea[delivery_area]` (EUR/MWh)
  - [ ] 2.5.4 Convert EUR/MWh to cents/kWh: `price_eur_mwh * 0.1`
  - [ ] 2.5.5 Parse timestamps to Python datetime objects (UTC-aware)
  - [ ] 2.5.6 Create `PriceInterval` instances

- [ ] 2.6 Add logging and error handling
  - [ ] 2.6.1 Log API request parameters (date, area, currency)
  - [ ] 2.6.2 Log response status and data availability
  - [ ] 2.6.3 Log number of intervals fetched
  - [ ] 2.6.4 Log conversion details (EUR/MWh → cents/kWh) for first interval

**Phase 2 Completion Criteria:**
- `NordPoolApi.fetch_prices()` returns list of `PriceInterval` objects
- Handles HTTP 200, 204, and error cases gracefully
- Price conversion is accurate (EUR/MWh × 0.1 = cents/kWh)
- All timestamps are UTC-aware datetime objects
- Comprehensive logging for debugging

---

## Phase 3: Template Processor ⏳

**Target:** 33% → 50%

- [ ] 3.1 Create `app/price_calculator.py` with template processor
  - [ ] 3.1.1 Create `TemplateProcessor` class
  - [ ] 3.1.2 Import `jinja2.sandbox.SandboxedEnvironment` for security
  - [ ] 3.1.3 Add constructor accepting `template_str` parameter

- [ ] 3.2 Implement template validation
  - [ ] 3.2.1 Parse template string with Jinja2 parser
  - [ ] 3.2.2 Catch `jinja2.TemplateSyntaxError` exceptions
  - [ ] 3.2.3 Log validation errors with template snippet and line number
  - [ ] 3.2.4 Raise exception to fail add-on startup on invalid template

- [ ] 3.3 Implement `calculate_price()` method
  - [ ] 3.3.1 Accept `marktprijs_cents` parameter (float)
  - [ ] 3.3.2 Create Jinja2 context dict: `{"marktprijs": marktprijs_cents}`
  - [ ] 3.3.3 Render template with context using sandboxed environment
  - [ ] 3.3.4 Parse rendered output as float
  - [ ] 3.3.5 Round to 4 decimal places using `round(price, 4)`

- [ ] 3.4 Add error handling for template rendering
  - [ ] 3.4.1 Catch `jinja2.TemplateError` during rendering
  - [ ] 3.4.2 Catch `ValueError` if output is not numeric
  - [ ] 3.4.3 Log errors with template context and input value
  - [ ] 3.4.4 Return `None` or raise exception (TBD: decide fail strategy)

- [ ] 3.5 Add unit tests for template processor
  - [ ] 3.5.1 Test valid template: `{{ marktprijs * 1.21 }}` (21% VAT)
  - [ ] 3.5.2 Test complex template with multiple operations
  - [ ] 3.5.3 Test invalid syntax: `{{ marktprijs *` (missing closing)
  - [ ] 3.5.4 Test non-numeric output: `{{ "invalid" }}`
  - [ ] 3.5.5 Test precision: verify 4 decimal rounding

- [ ] 3.6 Create default template examples for documentation
  - [ ] 3.6.1 Dutch import template: VAT (21%) + grid fee (€0.0248) + energy tax (€0.1228)
  - [ ] 3.6.2 Dutch export template: market price only (no fees)
  - [ ] 3.6.3 Document template variables and expected output format

**Phase 3 Completion Criteria:**
- Templates validated at processor initialization (fail-fast on syntax errors)
- `calculate_price()` returns float rounded to 4 decimals
- Template rendering errors logged with context
- Unit tests pass for valid/invalid templates
- Documentation includes working example templates

---

## Phase 4: Main Loop & Entity Management ⏳

**Target:** 50% → 67%

- [ ] 4.1 Create `app/main.py` with basic structure
  - [ ] 4.1.1 Import required modules (logging, signal, time, requests, json)
  - [ ] 4.1.2 Set up logging configuration
  - [ ] 4.1.3 Load configuration from environment/options

- [ ] 4.2 Implement configuration loading
  - [ ] 4.2.1 Read config from `/data/options.json` (HA pattern)
  - [ ] 4.2.2 Extract delivery_area, currency, timezone settings
  - [ ] 4.2.3 Extract import_price_template, export_price_template
  - [ ] 4.2.4 Extract fetch_interval_minutes
  - [ ] 4.2.5 Validate required fields are present

- [ ] 4.3 Initialize API clients and processors
  - [ ] 4.3.1 Create `NordPoolApi` instance
  - [ ] 4.3.2 Create `TemplateProcessor` for import template (validate here)
  - [ ] 4.3.3 Create `TemplateProcessor` for export template (validate here)
  - [ ] 4.3.4 Exit with error if template validation fails

- [ ] 4.4 Implement signal handlers for graceful shutdown
  - [ ] 4.4.1 Create `shutdown_flag` threading.Event
  - [ ] 4.4.2 Register SIGTERM handler
  - [ ] 4.4.3 Register SIGINT handler (Ctrl+C)
  - [ ] 4.4.4 Handlers set `shutdown_flag` and log shutdown message

- [ ] 4.5 Implement price fetching logic
  - [ ] 4.5.1 Calculate today's date (CET timezone)
  - [ ] 4.5.2 Calculate tomorrow's date
  - [ ] 4.5.3 Fetch today's prices via `nordpool_api.fetch_prices()`
  - [ ] 4.5.4 Fetch tomorrow's prices (handle HTTP 204 gracefully)
  - [ ] 4.5.5 Combine today + tomorrow intervals into single list
  - [ ] 4.5.6 Log total number of intervals fetched

- [ ] 4.6 Implement price calculation with templates
  - [ ] 4.6.1 Iterate through each `PriceInterval`
  - [ ] 4.6.2 Calculate import price using import template processor
  - [ ] 4.6.3 Calculate export price using export template processor
  - [ ] 4.6.4 Store results in new list with timestamps
  - [ ] 4.6.5 Handle template errors gracefully (log and skip interval)

- [ ] 4.7 Implement percentile calculations
  - [ ] 4.7.1 Extract all import prices into sorted list
  - [ ] 4.7.2 Calculate P05, P20, P40, P60, P80, P95 using `numpy.percentile()` or custom impl
  - [ ] 4.7.3 Store percentiles in dict for entity attributes

- [ ] 4.8 Implement price level classification
  - [ ] 4.8.1 Get current time (UTC)
  - [ ] 4.8.2 Find current price interval
  - [ ] 4.8.3 Compare current import price to P20/P40/P60
  - [ ] 4.8.4 Determine level: None (<P20), Low (P20-P40), Medium (P40-P60), High (>P60)

- [ ] 4.9 Implement Home Assistant entity management
  - [ ] 4.9.1 Create `create_or_update_entity()` helper function
  - [ ] 4.9.2 Get HA Supervisor token from environment
  - [ ] 4.9.3 Build HA API base URL (`http://supervisor/core/api`)
  - [ ] 4.9.4 POST to `/api/states/{entity_id}` with auth headers

- [ ] 4.10 Create/update price entities
  - [ ] 4.10.1 Create `sensor.ep_price_import` with current import price as state
  - [ ] 4.10.2 Add attributes: unit (cents/kWh), price_curve (48h data), percentiles
  - [ ] 4.10.3 Create `sensor.ep_price_export` with current export price as state
  - [ ] 4.10.4 Add attributes: unit (cents/kWh), price_curve (48h data)
  - [ ] 4.10.5 Create `sensor.ep_price_level` with classification (None/Low/Medium/High)
  - [ ] 4.10.6 Add attributes: p20, p40, p60 values, current_price

- [ ] 4.11 Implement main loop
  - [ ] 4.11.1 While not `shutdown_flag.is_set()`
  - [ ] 4.11.2 Fetch prices and calculate (steps 4.5-4.8)
  - [ ] 4.11.3 Update HA entities (steps 4.10)
  - [ ] 4.11.4 Log successful update with timestamp
  - [ ] 4.11.5 Sleep for `fetch_interval_minutes * 60` seconds (check shutdown_flag every second)
  - [ ] 4.11.6 Handle exceptions in loop (log and continue)

**Phase 4 Completion Criteria:**
- Main loop fetches prices every configured interval
- Graceful shutdown on SIGTERM/SIGINT
- Import/export prices calculated correctly
- Percentiles computed from price distribution
- Price level determined based on thresholds
- HA entities created with correct state and attributes
- All errors logged with context

---

## Phase 5: Testing & Documentation ⏳

**Target:** 67% → 83%

- [ ] 5.1 Create local testing environment
  - [ ] 5.1.1 Create `.env.example` file with required variables
  - [ ] 5.1.2 Create `run_local.py` script following charge-amps pattern
  - [ ] 5.1.3 Load environment variables from `.env` file
  - [ ] 5.1.4 Mock HA Supervisor API for local testing

- [ ] 5.2 Test Nord Pool API integration
  - [ ] 5.2.1 Test fetch for today's date (should return 96 intervals)
  - [ ] 5.2.2 Test fetch for tomorrow's date (may return 204)
  - [ ] 5.2.3 Verify price conversion accuracy (spot check EUR/MWh → cents/kWh)
  - [ ] 5.2.4 Verify UTC timestamp parsing

- [ ] 5.3 Test template processor
  - [ ] 5.3.1 Test valid import template with VAT calculation
  - [ ] 5.3.2 Test valid export template
  - [ ] 5.3.3 Test invalid syntax template (should fail at init)
  - [ ] 5.3.4 Test template with runtime error (should log and handle)
  - [ ] 5.3.5 Verify 4-decimal rounding

- [ ] 5.4 Test percentile calculations
  - [ ] 5.4.1 Create sample price data (known distribution)
  - [ ] 5.4.2 Calculate percentiles manually
  - [ ] 5.4.3 Verify code produces same results
  - [ ] 5.4.4 Test edge cases (all same price, very few intervals)

- [ ] 5.5 Test entity management
  - [ ] 5.5.1 Run add-on in HA dev instance
  - [ ] 5.5.2 Verify `sensor.ep_price_import` created
  - [ ] 5.5.3 Verify `sensor.ep_price_export` created
  - [ ] 5.5.4 Verify `sensor.ep_price_level` created
  - [ ] 5.5.5 Check entity attributes contain price_curve, percentiles
  - [ ] 5.5.6 Verify price curves have 48h data with UTC timestamps

- [ ] 5.6 Write comprehensive README
  - [ ] 5.6.1 Add overview and features section
  - [ ] 5.6.2 Add installation instructions (custom repo method)
  - [ ] 5.6.3 Document configuration options with examples
  - [ ] 5.6.4 Provide template examples for Dutch market
  - [ ] 5.6.5 Explain template variables (`marktprijs` in cents/kWh)
  - [ ] 5.6.6 Document created entities and their attributes
  - [ ] 5.6.7 Add troubleshooting section (template errors, API failures)
  - [ ] 5.6.8 Add local testing instructions

- [ ] 5.7 Document template examples
  - [ ] 5.7.1 **Dutch Import Example:**
    ```jinja2
    {% set marktprijs = marktprijs %}
    {% set opslag_inc = 2.48 %}
    {% set energiebelasting_inc = 12.28 %}
    {% set btw = 1.21 %}
    {{ (marktprijs * btw + opslag_inc + energiebelasting_inc) | round(4) }}
    ```
  - [ ] 5.7.2 **Dutch Export Example:**
    ```jinja2
    {{ marktprijs | round(4) }}
    ```
  - [ ] 5.7.3 Explain each component (VAT, grid fee, energy tax)

**Phase 5 Completion Criteria:**
- Local testing script runs successfully
- All unit tests pass
- Add-on installs and runs in HA dev instance
- Entities appear in HA with correct data
- README is comprehensive and includes working examples
- Template documentation is clear and accurate

---

## Phase 6: Integration & Polish ⏳

**Target:** 83% → 100%

- [ ] 6.1 Update root repository metadata
  - [ ] 6.1.1 Update `repository.json` with new add-on entry
  - [ ] 6.1.2 Update root `README.md` with energy-prices add-on description
  - [ ] 6.1.3 Add link to energy-prices README

- [ ] 6.2 Update documentation site materials
  - [ ] 6.2.1 Update `docs/price-helper-service-addon.md` to reflect actual implementation
  - [ ] 6.2.2 Add architecture diagram if helpful
  - [ ] 6.2.3 Document dependent add-ons (future: battery optimizer, etc.)

- [ ] 6.3 End-to-end testing
  - [ ] 6.3.1 Fresh install in HA instance
  - [ ] 6.3.2 Configure with Dutch templates
  - [ ] 6.3.3 Verify prices fetched and entities created
  - [ ] 6.3.4 Check logs for errors or warnings
  - [ ] 6.3.5 Test graceful shutdown (restart add-on)
  - [ ] 6.3.6 Test template modification (update config, restart)
  - [ ] 6.3.7 Test invalid template (should fail to start)

- [ ] 6.4 Performance validation
  - [ ] 6.4.1 Monitor memory usage over 24h period
  - [ ] 6.4.2 Monitor CPU usage during fetch/calculation
  - [ ] 6.4.3 Verify no memory leaks (stable over time)
  - [ ] 6.4.4 Check log file size growth

- [ ] 6.5 Final polish
  - [ ] 6.5.1 Review all log messages (clarity, level, frequency)
  - [ ] 6.5.2 Add comments to complex code sections
  - [ ] 6.5.3 Verify all TODOs removed or documented
  - [ ] 6.5.4 Run linter (ruff/black) on Python code
  - [ ] 6.5.5 Remove debug logging or set to appropriate level

- [ ] 6.6 Create demo materials (optional)
  - [ ] 6.6.1 Screenshot of HA entities with price data
  - [ ] 6.6.2 Screenshot of price curve graph in HA dashboard
  - [ ] 6.6.3 Example automation using price level sensor

- [ ] 6.7 Version and release
  - [ ] 6.7.1 Set version to `1.0.0` in config.yaml
  - [ ] 6.7.2 Create CHANGELOG.md with release notes
  - [ ] 6.7.3 Tag release in git
  - [ ] 6.7.4 Test add-on installation from GitHub repository

**Phase 6 Completion Criteria:**
- Root repository documentation updated
- Add-on appears in HA add-on store
- End-to-end flow works flawlessly
- Performance is acceptable (low CPU/memory)
- Code is clean and well-documented
- Ready for production use

---

## Overall Progress

**📋 PENDING (6 of 6 phases):**
- Phase 1: Add-on Structure & Configuration
- Phase 2: Nord Pool API Client
- Phase 3: Template Processor
- Phase 4: Main Loop & Entity Management
- Phase 5: Testing & Documentation
- Phase 6: Integration & Polish

**Progress: 0%** (0 of 84 tasks completed)

---

## Notes

### Task Conventions
- `[x]` = Completed task (add timestamp when done)
- `[-]` = In progress task
- `[ ]` = Not started task

### Update Schedule
- Update this file after completing each major task
- Update proposal.md status percentage at phase boundaries
- Create STATUS.md at 25% and 50% milestones if needed

### Questions/Blockers
- TBD: Decide template rendering error strategy (return None vs raise exception)
- TBD: Decide if custom percentile thresholds needed in v1.0 (currently hardcoded)
