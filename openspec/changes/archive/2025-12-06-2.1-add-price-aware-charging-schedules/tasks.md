# Tasks - Price-Aware Charge Amps Scheduling (Version 2.1)

## Status
⏳ PLANNING - 0%

## Phase 1: Configuration & Plumbing
- [ ] 1.1 Extend `config.yaml` options/schema with automation toggle, price sensor entity, required_minutes_per_day, earliest_start_hour, latest_end_hour, max_current_per_phase, connector_ids, and optional safety margin minutes.
- [ ] 1.2 Update `run_local.py`, `run_addon.py`, and env loading helpers so new options are available for local testing (with sensible defaults if unset).
- [ ] 1.3 Document every new option in `charge-amps-monitor/README.md` and ensure values validate via Supervisor schema (e.g., minutes multiple of 15, start < end).

## Phase 2: Price Curve Analysis
- [ ] 2.1 Create `app/price_window_planner.py` that reads a HA entity via `HomeAssistantApi`, extracts the `price_curve` attribute, and normalizes it into 15-minute buckets in HA’s timezone.
- [ ] 2.2 Implement cheapest-window selection supporting contiguous windows, earliest/latest hour fences, daylight-saving transitions, and fallback when only today’s data exists.
- [ ] 2.3 Add unit tests for the planner covering missing curves, partial days, negative prices, and multi-day comparisons.

## Phase 3: Charge Amps Schedule Client
- [ ] 3.1 Extend `ChargerApi` with `get_schedules`, `upsert_schedule`, and `delete_schedule` helpers that wrap the `/api/smartChargingSchedules` GET/PUT/DELETE calls captured in the HAR files.
- [ ] 3.2 Persist automation metadata (schedule id, connector id, last hash) under `/data/automation_schedule.json` to detect drift and keep user-created schedules untouched.
- [ ] 3.3 Add retries + structured logging around schedule writes, including mapping HA timezone slots to the `from`/`to` second offsets Charge Amps expects.

## Phase 4: Automation Loop & HA Integration
- [ ] 4.1 Build a scheduler coordinator in `app/main.py` that waits until tomorrow’s prices publish, creates the plan once per day, and re-validates hourly while automation is enabled.
- [ ] 4.2 Publish helper entities (status text + next_start + next_end + last_error) via MQTT discovery/REST and add a `charge_amps.force_schedule_refresh` service or command for manual retries.
- [ ] 4.3 Respect manual overrides: if automation toggle changes to false, delete the automation schedule, stop reconciliation, and emit a paused status.

## Phase 5: Testing, Docs & Release
- [ ] 5.1 Extend automated tests (unit + smoke) to cover new modules and add a mocked integration test for the scheduler coordinator.
- [ ] 5.2 Update CHANGELOG, add-on README, repository metadata, and sample dashboards to describe the automation workflow and new sensors.
- [ ] 5.3 Validate end-to-end with `run_addon.py --addon charge-amps-monitor --once` using mocked price data + API responses, then bump add-on version.
