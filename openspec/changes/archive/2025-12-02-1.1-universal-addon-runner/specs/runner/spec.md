# Runner Capability - Specification (Delta)

## ADDED Requirements

### Requirement: Add-on Discovery
The system SHALL list add-ons by scanning subdirectories that contain `config.yaml` and extract their `slug` and `name`.

#### Scenario: List add-ons
- WHEN the developer runs `python run_addon.py --list`
- THEN the system returns all add-ons with their slug and path

### Requirement: Environment Loading & Token Normalization
The system SHALL load environment variables from an explicit file argument, or `.env.<slug>` at repository root, or `<addon>/.env` as fallback.
The system MUST normalize HA tokens such that if either `SUPERVISOR_TOKEN` or `HA_API_TOKEN` is provided, both are set in the process environment.

#### Scenario: Env precedence
- WHEN both `.env.<slug>` and `<addon>/.env` exist
- THEN `.env.<slug>` is used

#### Scenario: Token normalization
- WHEN only `SUPERVISOR_TOKEN` is present
- THEN `HA_API_TOKEN` is set to the same value

### Requirement: Validation & Execution
The system SHALL validate required env vars for each add-on and fail with a clear message if missing.
The system SHALL execute the add-on by launching its existing `run_local.py` in the add-on directory; if absent, it MUST run `app/main.py` with `PYTHONPATH` set accordingly.

#### Scenario: Run charge-amps-monitor
- WHEN required env vars are present
- THEN `run_local.py` executes with the add-on as the working directory

## Acceptance Criteria
- [ ] Discovery returns add-ons with slug and path
- [ ] Env file precedence and token normalization work
- [ ] Validation errors list missing keys explicitly
- [ ] Execution runs existing scripts without code changes in add-ons
