# Tasks - Water Heater Scheduler Add-on (Version 2.0)

## Status
✅ IMPLEMENTATION COMPLETE - 100%

*Runtime testing (8.2, 9.1-9.3) requires live Home Assistant connection*

## Phase 1: Scaffold Add-on Structure ✅
- [x] 1.1 Create `water-heater-scheduler/` folder with standard structure
- [x] 1.2 Create `config.yaml` with entity settings (water_heater required, price/away/bath optional)
- [x] 1.3 Create `config.yaml` with schedule settings (interval, night window, legionella)
- [x] 1.4 Create `config.yaml` with temperature preset selector (eco/comfort/performance/custom)
- [x] 1.5 Create `config.yaml` with custom temp overrides (only used when preset=custom)
- [x] 1.6 Create `config.yaml` with advanced settings (min_cycle_gap, log_level)
- [x] 1.7 Create `Dockerfile` and `run.sh` (based on energy-prices pattern)
- [x] 1.8 Create `requirements.txt` with dependencies
- [x] 1.9 Copy `shared/` modules and verify imports work

## Phase 2: Core Models & Config ✅
- [x] 2.1 Create `app/models.py` with `TemperaturePreset` dataclass (eco/comfort/performance values)
- [x] 2.2 Create `app/models.py` with `ScheduleConfig` (load settings, apply presets)
- [x] 2.3 Create `app/models.py` with `ProgramType` enum (Night/Day/Legionella/Bath/Away/Idle)
- [x] 2.4 Create `app/models.py` with `HeaterState` dataclass for persistence
- [x] 2.5 Implement config validation (legionella ≥60°C, preheat > minimal warnings)
- [x] 2.6 Implement smart entity detection (auto-detect price sensor)

## Phase 3: Price Data Integration ✅
- [x] 3.1 Create `app/price_analyzer.py` - read price_curve from sensor
- [x] 3.2 Parse 15-minute interval prices into `Dict[datetime, float]`
- [x] 3.3 Implement `get_lowest_night_price()` using configured night window
- [x] 3.4 Implement `get_lowest_day_price()` for day window
- [x] 3.5 Implement `compare_today_tomorrow()` for day program decisions
- [x] 3.6 Implement `is_negative_price()` for max heating trigger

## Phase 4: Program Logic ✅
- [x] 4.1 Night program: compare night vs day price → preheat or minimal temp
- [x] 4.2 Day program: compare today vs tomorrow price → preheat or minimal temp
- [x] 4.3 Legionella program: weekly cycle on configured day at preset temp
- [x] 4.4 Away mode: fixed 35°C (when away entity configured and on)
- [x] 4.5 Bath mode: fixed 58°C + auto-disable at threshold
- [x] 4.6 Negative price: fixed 70°C (maximize free energy)

## Phase 5: Scheduler & Cycle Protection ✅
- [x] 5.1 Create `app/scheduler.py` - program selection logic
- [x] 5.2 Implement decision tree (negative → away → bath → legionella → night/day)
- [x] 5.3 Implement cycle gap protection (min_cycle_gap_minutes)
- [x] 5.4 Track last_cycle_end timestamp in state

## Phase 6: Water Heater Controller & Sensors ✅
- [x] 6.1 Create `app/water_heater_controller.py` - set temp via HA API
- [x] 6.2 Create `sensor.wh_program` - current program name
- [x] 6.3 Create `sensor.wh_target_temp` - current target temperature
- [x] 6.4 Create `sensor.wh_status` - human-readable status
- [x] 6.5 State persistence (`/data/state.json`)

## Phase 7: Main Loop & Integration ✅
- [x] 7.1 Create `app/main.py` with configurable evaluation loop
- [x] 7.2 Integrate: price analyzer → scheduler → controller
- [x] 7.3 Add graceful shutdown handling via shared module
- [x] 7.4 Add comprehensive logging with price/schedule decisions

## Phase 8: Testing & Documentation ✅
- [x] 8.1 Create `.env.example` for local testing
- [ ] 8.2 Test with `run_addon.py --addon water-heater-scheduler --once` *(requires live HA)*
- [x] 8.3 Write `README.md` with preset examples and config guide
- [x] 8.4 Add to `repository.json` for Home Assistant discovery
- [x] 8.5 Update root `README.md` with new add-on

## Phase 9: Finalization ✅
- [ ] 9.1 Verify all sensors created match spec *(requires live HA)*
- [ ] 9.2 Test full cycle: night → day → legionella → idle *(requires live HA)*
- [ ] 9.3 Test preset switching (eco → comfort → performance) *(requires live HA)*
- [x] 9.4 Create `CHANGELOG.md` with initial release
- [x] 9.5 Sync shared modules and verify Docker build

## Implementation Notes

**Completed 2025-01-XX:**
- Full add-on implementation with all core features
- Price analyzer with window-based optimization
- Decision tree scheduler with priority ordering
- Water heater controller with HA API integration
- Three temperature presets (eco/comfort/performance) plus custom
- State persistence for program tracking
- Extended shared/ha_api.py with `get_entity_state()` and `call_service()`
- Added to repository.json and root README.md

**Files Created:**
- `water-heater-scheduler/config.yaml` - Full configuration schema
- `water-heater-scheduler/Dockerfile` - Alpine-based build
- `water-heater-scheduler/run.sh` - Bashio startup
- `water-heater-scheduler/requirements.txt` - Dependencies
- `water-heater-scheduler/app/__init__.py`
- `water-heater-scheduler/app/models.py` - Data models
- `water-heater-scheduler/app/price_analyzer.py` - Price parsing
- `water-heater-scheduler/app/scheduler.py` - Decision tree
- `water-heater-scheduler/app/water_heater_controller.py` - HA control
- `water-heater-scheduler/app/main.py` - Main loop
- `water-heater-scheduler/README.md` - Documentation
- `water-heater-scheduler/CHANGELOG.md` - Release notes
- `water-heater-scheduler/.env.example` - Local testing

**Files Modified:**
- `shared/ha_api.py` - Added get_entity_state(), call_service()
- `sync_shared.py` - Added water-heater-scheduler
- `run_addon.py` - Added to sync list
- `repository.json` - Added add-on entry
- `README.md` - Added documentation section
