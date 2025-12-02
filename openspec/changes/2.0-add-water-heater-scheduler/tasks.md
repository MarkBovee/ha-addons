# Tasks - Water Heater Scheduler Add-on (Version 2.0)

## Status
🟡 NOT STARTED - 0%

## Phase 1: Scaffold Add-on Structure
- [ ] 1.1 Create `water-heater-scheduler/` folder with standard structure
- [ ] 1.2 Create `config.yaml` with entity settings (water_heater required, price/away/bath optional)
- [ ] 1.3 Create `config.yaml` with schedule settings (interval, night window, legionella)
- [ ] 1.4 Create `config.yaml` with temperature preset selector (eco/comfort/performance/custom)
- [ ] 1.5 Create `config.yaml` with custom temp overrides (only used when preset=custom)
- [ ] 1.6 Create `config.yaml` with advanced settings (min_cycle_gap, log_level)
- [ ] 1.7 Create `Dockerfile` and `run.sh` (based on energy-prices pattern)
- [ ] 1.8 Create `requirements.txt` with dependencies
- [ ] 1.9 Copy `shared/` modules and verify imports work

## Phase 2: Core Models & Config
- [ ] 2.1 Create `app/models.py` with `TemperaturePreset` dataclass (eco/comfort/performance values)
- [ ] 2.2 Create `app/models.py` with `ScheduleConfig` (load settings, apply presets)
- [ ] 2.3 Create `app/models.py` with `ProgramType` enum (Night/Day/Legionella/Bath/Away/Idle)
- [ ] 2.4 Create `app/models.py` with `HeaterState` dataclass for persistence
- [ ] 2.5 Implement config validation (legionella ≥60°C, preheat > minimal warnings)
- [ ] 2.6 Implement smart entity detection (auto-detect price sensor)

## Phase 3: Price Data Integration
- [ ] 3.1 Create `app/price_analyzer.py` - read price_curve from sensor
- [ ] 3.2 Parse 15-minute interval prices into `Dict[datetime, float]`
- [ ] 3.3 Implement `get_lowest_night_price()` using configured night window
- [ ] 3.4 Implement `get_lowest_day_price()` for day window
- [ ] 3.5 Implement `compare_today_tomorrow()` for day program decisions
- [ ] 3.6 Implement `is_negative_price()` for max heating trigger

## Phase 4: Program Logic
- [ ] 4.1 Night program: compare night vs day price → preheat or minimal temp
- [ ] 4.2 Day program: compare today vs tomorrow price → preheat or minimal temp
- [ ] 4.3 Legionella program: weekly cycle on configured day at preset temp
- [ ] 4.4 Away mode: fixed 35°C (when away entity configured and on)
- [ ] 4.5 Bath mode: fixed 58°C + auto-disable at threshold
- [ ] 4.6 Negative price: fixed 70°C (maximize free energy)

## Phase 5: Scheduler & Cycle Protection
- [ ] 5.1 Create `app/scheduler.py` - program selection logic
- [ ] 5.2 Implement decision tree (negative → away → bath → legionella → night/day)
- [ ] 5.3 Implement cycle gap protection (min_cycle_gap_minutes)
- [ ] 5.4 Track last_cycle_end timestamp in state

## Phase 6: Water Heater Controller & Sensors
- [ ] 6.1 Create `app/water_heater_controller.py` - set temp via HA API
- [ ] 6.2 Create `sensor.wh_program` - current program name
- [ ] 6.3 Create `sensor.wh_target_temp` - current target temperature
- [ ] 6.4 Create `sensor.wh_status` - human-readable status
- [ ] 6.5 State persistence (`/data/state.json`)

## Phase 7: Main Loop & Integration
- [ ] 7.1 Create `app/main.py` with configurable evaluation loop
- [ ] 7.2 Integrate: price analyzer → scheduler → controller
- [ ] 7.3 Add graceful shutdown handling via shared module
- [ ] 7.4 Add comprehensive logging with price/schedule decisions

## Phase 8: Testing & Documentation
- [ ] 8.1 Create `.env.example` for local testing
- [ ] 8.2 Test with `run_addon.py --addon water-heater-scheduler --once`
- [ ] 8.3 Write `README.md` with preset examples and config guide
- [ ] 8.4 Add to `repository.json` for Home Assistant discovery
- [ ] 8.5 Update root `README.md` with new add-on

## Phase 9: Finalization
- [ ] 9.1 Verify all sensors created match spec
- [ ] 9.2 Test full cycle: night → day → legionella → idle
- [ ] 9.3 Test preset switching (eco → comfort → performance)
- [ ] 9.4 Create `CHANGELOG.md` with initial release
- [ ] 9.5 Sync shared modules and verify Docker build
