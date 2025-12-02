# Tasks - Water Heater Scheduler Add-on (Version 2.0)

## Status
🟡 NOT STARTED - 0%

## Phase 1: Scaffold Add-on Structure
- [ ] 1.1 Create `water-heater-scheduler/` folder with standard structure
- [ ] 1.2 Create `config.yaml` with all user settings from spec
- [ ] 1.3 Create `Dockerfile` and `run.sh` (based on energy-prices pattern)
- [ ] 1.4 Create `requirements.txt` with dependencies
- [ ] 1.5 Copy `shared/` modules and verify imports work

## Phase 2: Core Scheduling Logic
- [ ] 2.1 Create `app/models.py` with `ScheduleConfig`, `ProgramType`, `HeaterState` dataclasses
- [ ] 2.2 Create `app/price_analyzer.py` - find lowest night/day price windows
- [ ] 2.3 Create `app/scheduler.py` - determine program type (Night/Day/Legionella/Away/Idle)
- [ ] 2.4 Create `app/water_heater_controller.py` - set temperature and operation mode via HA API
- [ ] 2.5 Implement wait cycle logic for smooth transitions

## Phase 3: Price Data Integration
- [ ] 3.1 Read price curves from `sensor.ep_price_import` attributes
- [ ] 3.2 Parse 15-minute interval prices into `Dict[datetime, float]`
- [ ] 3.3 Implement `get_lowest_night_price()` (00:00-06:00 window)
- [ ] 3.4 Implement `get_lowest_day_price()` (06:00-24:00 window)
- [ ] 3.5 Implement tomorrow price comparison for day program decisions

## Phase 4: Program Logic (from WaterHeater.cs)
- [ ] 4.1 Night program: target 52-56°C based on night vs day price comparison
- [ ] 4.2 Day program: target 58-70°C based on price level
- [ ] 4.3 Legionella program: target 60-66°C, 3-hour duration on configured day
- [ ] 4.4 Away mode: reduced temperatures with legionella protection
- [ ] 4.5 Bath mode override: auto-disable when water temp > 50°C

## Phase 5: State & Entity Management
- [ ] 5.1 Create state persistence (`/data/state.json`) for heater_on, target_temp, wait_cycles
- [ ] 5.2 Update `input_text.heating_schedule_status` with program info
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
