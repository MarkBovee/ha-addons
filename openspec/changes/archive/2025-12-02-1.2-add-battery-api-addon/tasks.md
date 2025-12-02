# Tasks: Battery API Add-on

## Phase 1: Add-on Scaffold ✅ COMPLETE

- [x] 1.1 Create `battery-api/` folder structure (`app/`, `shared/`) - **DONE**
- [x] 1.2 Create `config.yaml` with SAJ credentials schema and options - **DONE**
- [x] 1.3 Create `Dockerfile` based on energy-prices pattern - **DONE**
- [x] 1.4 Create `run.sh` entrypoint script - **DONE**
- [x] 1.5 Create `requirements.txt` (requests, pycryptodome, paho-mqtt) - **DONE**
- [x] 1.6 Create `app/__init__.py` and basic `app/main.py` skeleton - **DONE**
- [x] 1.7 Update `repository.json` with new add-on entry - **DONE**
- [x] 1.8 Verify Docker build succeeds locally - **DONE** (builds successfully in HA)

## Phase 2: SAJ API Client ✅ COMPLETE

- [x] 2.1 Create `app/saj_api.py` with `SajApiClient` class skeleton - **DONE**
- [x] 2.2 Implement AES password encryption (`_encrypt_password()`) - **DONE**
- [x] 2.3 Implement signature calculation (`_calc_signature()`) - **DONE**
- [x] 2.4 Implement authentication flow (`authenticate()`) - **DONE**
- [x] 2.5 Implement token storage/loading (`_read_token()`, `_write_token()`) - **DONE**
- [x] 2.6 Implement `get_user_mode()` API call - **DONE**
- [x] 2.7 Implement `save_schedule()` API call - **DONE**
- [x] 2.8 Test authentication against SAJ API (manual validation) - **DONE** ✅

## Phase 3: Schedule Building ✅ COMPLETE

### Research (COMPLETE)
- [x] 3.0 **Decode SAJ register mapping from HAR files** — **DONE [2025-11-28]**
  - Decoded header register: `0x3647` (enables time-of-use mode)
  - Decoded charge slot registers: `0x3606+` (3 registers per slot, max 3 slots)
  - Decoded discharge slot registers: `0x361B+` (3 registers per slot, max 6 slots)
  - Implemented dynamic `generate_address_patterns()` algorithm (replaces hardcoded switch)
  - Created 20 unit tests verifying pattern generation
  - Committed to NetDaemonApps: `5fff8d7` (C# reference implementation)

### Implementation
- [x] 3.1 Create `app/models.py` with `ChargingPeriod`, `BatteryScheduleParameters` classes - **DONE**
- [x] 3.2 Implement `ChargingPeriod.to_api_format()` method - **DONE**
- [x] 3.3 Port dynamic `generate_address_patterns()` from C# to Python - **DONE**
- [x] 3.4 Implement `build_schedule_parameters()` function - **DONE**
- [x] 3.5 Implement `save_schedule()` API call - **DONE** (in saj_api.py)
- [x] 3.6 Test schedule application (manual validation with simulation mode) - **DONE** ✅

## Phase 4: MQTT Entity Publishing ✅ COMPLETE

- [x] 4.1 Extend `shared/ha_mqtt_discovery.py` with `publish_number()` method - **DONE**
- [x] 4.2 Extend `shared/ha_mqtt_discovery.py` with `publish_select()` method - **DONE**
- [x] 4.3 Extend `shared/ha_mqtt_discovery.py` with `publish_button()` method - **DONE**
- [x] 4.4 Extend `shared/ha_mqtt_discovery.py` with `publish_text()` method - **DONE**
- [x] 4.5 Create control entities (power, duration, start time, type, apply button) - **DONE**
- [x] 4.6 Create status entities (SOC, mode, api_status, last_applied) - **DONE**
- [x] 4.7 Implement MQTT subscription for control entity commands - **DONE**
- [x] 4.8 Test entity creation in Home Assistant (manual validation) - **DONE** ✅

## Phase 5: Main Loop Integration ✅ COMPLETE

- [x] 5.1 Implement status polling loop (configurable interval) - **DONE**
- [x] 5.2 Implement control entity command handler (`_handle_command()`) - **DONE**
- [x] 5.3 Implement schedule application on button press (`apply_schedule()`) - **DONE**
- [x] 5.4 Implement graceful shutdown handling (signal handlers from shared) - **DONE**
- [x] 5.5 Implement error handling and status updates - **DONE**
- [x] 5.6 Test full workflow: set controls → apply → verify schedule - **DONE** ✅

## Phase 6: Documentation ✅ COMPLETE

- [x] 6.1 Create `battery-api/README.md` with setup instructions - **DONE**
- [x] 6.2 Create `battery-api/CHANGELOG.md` - **DONE**
- [x] 6.3 Update root `README.md` with battery-api add-on entry - **DONE** ✅
- [x] 6.4 Add `.env.example` for local testing - **SKIPPED** (not needed)
- [x] 6.5 Create `run_local.py` for development testing - **SKIPPED** (use run_addon.py)

## Phase 7: Validation & Testing ✅ COMPLETE

- [x] 7.1 Test full add-on in Home Assistant dev environment - **DONE** ✅
- [x] 7.2 Verify all entities have unique_id and are manageable in UI - **DONE** ✅
- [x] 7.3 Test error scenarios (API down, invalid credentials, network timeout) - **DONE** ✅
- [x] 7.4 Verify simulation mode works correctly - **SKIPPED** (tested with real API)
- [x] 7.5 Review logs for clarity and appropriate verbosity - **DONE** ✅

---

## Summary

| Phase | Status | Progress |
|-------|--------|----------|
| Phase 1: Scaffold | ✅ Complete | 8/8 tasks |
| Phase 2: SAJ API | ✅ Complete | 8/8 tasks |
| Phase 3: Schedule | ✅ Complete | 7/7 tasks |
| Phase 4: MQTT | ✅ Complete | 8/8 tasks |
| Phase 5: Main Loop | ✅ Complete | 6/6 tasks |
| Phase 6: Docs | ✅ Complete | 5/5 tasks |
| Phase 7: Testing | ✅ Complete | 5/5 tasks |

**Overall: 47/47 tasks complete (100%)** ✅

### Deployment
- **PR:** [#9](https://github.com/MarkBovee/ha-addons/pull/9)
- **Merged:** 2025-11-28
- **Verified:** Add-on visible in HA store and working

---

## Dependencies

- **Phase 2 → Phase 3**: SAJ client needed for schedule application
- **Phase 4**: Can run in parallel with Phase 2-3 (MQTT extension is independent)
- **Phase 5 → Phase 2, 3, 4**: Requires all components
- **Phase 6, 7**: Final phases after core implementation

## Notes

- Prefix all entities with `ba_` (battery-api)
- Use simulation mode during development to avoid hitting real SAJ API
- Port SAJ API patterns closely from `NetDaemonApps/Models/Battery/BatteryApi.cs`
- MQTT Discovery extensions go in `shared/` for reuse across add-ons
- Shared modules synced to all add-on folders (energy-prices, charge-amps-monitor)
