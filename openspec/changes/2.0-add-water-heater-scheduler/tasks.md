# Tasks - Water Heater Scheduler Add-on (Version 2.0)

## Status
🟡 NOT STARTED - 0%

## Phase 1: Scaffold Add-on Structure
- [ ] 1.1 Create `water-heater-scheduler/` folder with standard structure
- [ ] 1.2 Create `config.yaml` with entity selectors (price, water_heater, away, bath, status)
- [ ] 1.3 Create `config.yaml` schedule settings (interval, night window, legionella day/duration)
- [ ] 1.4 Create `config.yaml` temperature settings (all 10 temp configs with defaults/ranges)
- [ ] 1.5 Create `config.yaml` advanced settings (wait_cycles, cheap_threshold, log_level)
- [ ] 1.6 Create `Dockerfile` and `run.sh` (based on energy-prices pattern)
- [ ] 1.7 Create `requirements.txt` with dependencies
- [ ] 1.8 Copy `shared/` modules and verify imports work

## Phase 2: Core Scheduling Logic
- [ ] 2.1 Create `app/models.py` with `ScheduleConfig` (load all settings from config)
- [ ] 2.2 Create `app/models.py` with `ProgramType` enum and `HeaterState` dataclass
- [ ] 2.3 Create `app/price_analyzer.py` - find lowest night/day price windows
- [ ] 2.4 Create `app/scheduler.py` - determine program type using config temps
- [ ] 2.5 Create `app/water_heater_controller.py` - set temperature via HA API
- [ ] 2.6 Implement wait cycle logic using `wait_cycles_limit` config

## Phase 3: Price Data Integration
- [ ] 3.1 Read price curves from configured `price_sensor_entity_id` attributes
- [ ] 3.2 Parse 15-minute interval prices into `Dict[datetime, float]`
- [ ] 3.3 Implement `get_lowest_night_price()` using configured night window
- [ ] 3.4 Implement `get_lowest_day_price()` using configured night window end
- [ ] 3.5 Implement tomorrow price comparison (when `next_day_price_check` enabled)

## Phase 4: Program Logic (from WaterHeater.cs)
- [ ] 4.1 Night program: use config temps (`night_high_temp`, `night_low_temp`, `night_min_temp`)
- [ ] 4.2 Day program: use config temps based on `high_price_gap_threshold` comparison
- [ ] 4.3 Legionella program: use config temps and `legionella_day`
- [ ] 4.4 Away mode: use `away_night_temp`, `away_day_temp` with legionella protection
- [ ] 4.5 Bath mode: use `bath_target_temp`, `bath_recovery_temp`, auto-disable threshold

## Phase 5: State & Entity Management
- [ ] 5.1 Create state persistence (`/data/state.json`) for heater_on, target_temp, wait_cycles
- [ ] 5.2 Update configured `schedule_status_entity_id` with program info
- [ ] 5.3 Create `sensor.wh_next_start` and `sensor.wh_next_end` timestamp sensors
- [ ] 5.4 Create `sensor.wh_target_temp` and `sensor.wh_program_type` sensors

## Phase 6: Main Loop & Integration
- [ ] 6.1 Create `app/main.py` with 5-minute evaluation loop
- [ ] 6.2 Integrate all components (price analyzer → scheduler → controller)
- [ ] 6.3 Add graceful shutdown handling via shared module
- [ ] 6.4 Add comprehensive logging with price/schedule decisions

## Phase 7: Testing & Documentation
- [ ] 7.1 Create `.env.example` for local testing
- [ ] 7.2 Test with `run_addon.py --addon water-heater-scheduler --once`
- [ ] 7.3 Write `README.md` with configuration examples
- [ ] 7.4 Add to `repository.json` for Home Assistant discovery
- [ ] 7.5 Update root `README.md` with new add-on

## Phase 8: Finalization
- [ ] 8.1 Verify all entities created match spec
- [ ] 8.2 Test full cycle: night → day → legionella → idle
- [ ] 8.3 Create `CHANGELOG.md` with initial release
- [ ] 8.4 Sync shared modules and verify Docker build
