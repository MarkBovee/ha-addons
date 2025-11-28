# Tasks: Battery API Add-on

## Phase 1: Add-on Scaffold ✅ Ready

- [ ] 1.1 Create `battery-api/` folder structure (`app/`, `shared/`)
- [ ] 1.2 Create `config.yaml` with SAJ credentials schema and options
- [ ] 1.3 Create `Dockerfile` based on energy-prices pattern
- [ ] 1.4 Create `run.sh` entrypoint script
- [ ] 1.5 Create `requirements.txt` (requests, pycryptodome, paho-mqtt)
- [ ] 1.6 Create `app/__init__.py` and basic `app/main.py` skeleton
- [ ] 1.7 Update `repository.json` with new add-on entry
- [ ] 1.8 Verify Docker build succeeds locally

## Phase 2: SAJ API Client ⏳ Pending

- [ ] 2.1 Create `app/saj_api.py` with `SajApiClient` class skeleton
- [ ] 2.2 Implement AES password encryption (`encrypt_password()`)
- [ ] 2.3 Implement signature calculation (`calc_signature()`)
- [ ] 2.4 Implement authentication flow (`authenticate()`)
- [ ] 2.5 Implement token storage/loading (`read_token()`, `write_token()`)
- [ ] 2.6 Implement `get_user_mode()` API call
- [ ] 2.7 Implement `get_device_status()` for SOC and power data
- [ ] 2.8 Test authentication against SAJ API (manual validation)

## Phase 3: Schedule Building 🟡 In Progress

### Research (COMPLETE)
- [x] 3.0 **Decode SAJ register mapping from HAR files** — **DONE [2025-11-28]**
  - Decoded header register: `0x3647` (enables time-of-use mode)
  - Decoded charge slot registers: `0x3606+` (3 registers per slot, max 3 slots)
  - Decoded discharge slot registers: `0x361B+` (3 registers per slot, max 6 slots)
  - Implemented dynamic `generate_address_patterns()` algorithm (replaces hardcoded switch)
  - Created 20 unit tests verifying pattern generation
  - Committed to NetDaemonApps: `5fff8d7` (C# reference implementation)

### Implementation
- [ ] 3.1 Create `app/models.py` with `ChargingPeriod`, `ChargingSchema` classes
- [ ] 3.2 Implement `ChargingPeriod.to_api_format()` method
- [ ] 3.3 Port dynamic `generate_address_patterns()` from C# to Python
- [ ] 3.4 Implement `build_schedule_parameters()` function
- [ ] 3.5 Implement `save_schedule()` API call
- [ ] 3.6 Test schedule application (manual validation with simulation mode)

## Phase 4: MQTT Entity Publishing ⏳ Pending

- [ ] 4.1 Extend `shared/ha_mqtt_discovery.py` with `publish_number()` method
- [ ] 4.2 Extend `shared/ha_mqtt_discovery.py` with `publish_select()` method
- [ ] 4.3 Extend `shared/ha_mqtt_discovery.py` with `publish_button()` method
- [ ] 4.4 Extend `shared/ha_mqtt_discovery.py` with `publish_text()` method
- [ ] 4.5 Create control entities (power, duration, start time, type, apply button)
- [ ] 4.6 Create status entities (SOC, mode, direction, schedule, api_status)
- [ ] 4.7 Implement MQTT subscription for control entity commands
- [ ] 4.8 Test entity creation in Home Assistant (manual validation)

## Phase 5: Main Loop Integration ⏳ Pending

- [ ] 5.1 Implement status polling loop (60s interval)
- [ ] 5.2 Implement control entity command handler
- [ ] 5.3 Implement schedule application on button press
- [ ] 5.4 Implement graceful shutdown handling (SIGTERM/SIGINT)
- [ ] 5.5 Implement error handling and status updates
- [ ] 5.6 Test full workflow: set controls → apply → verify schedule

## Phase 6: Documentation ⏳ Pending

- [ ] 6.1 Create `battery-api/README.md` with setup instructions
- [ ] 6.2 Create `battery-api/CHANGELOG.md`
- [ ] 6.3 Update root `README.md` with battery-api add-on entry
- [ ] 6.4 Add `.env.example` for local testing
- [ ] 6.5 Create `run_local.py` for development testing

## Phase 7: Validation & Testing ⏳ Pending

- [ ] 7.1 Test full add-on in Home Assistant dev environment
- [ ] 7.2 Verify all entities have unique_id and are manageable in UI
- [ ] 7.3 Test error scenarios (API down, invalid credentials, network timeout)
- [ ] 7.4 Verify simulation mode works correctly
- [ ] 7.5 Review logs for clarity and appropriate verbosity

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
