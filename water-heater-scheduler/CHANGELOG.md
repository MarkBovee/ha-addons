# Changelog

All notable changes to the Water Heater Scheduler add-on will be documented in this file.

## [1.2.9] - 2025-12-08

### Changed
- **Day skip logic now matches NetDaemon WaterHeater.cs**:
  - Compares **current price** vs **tomorrow's night average** (00:00-06:00)
  - Only skips day heating if: tomorrow night is cheaper AND current price > €0.20 (Medium)
  - This prevents skipping when prices are already low
  - Status shows `⏭️ Skipping day | Tomorrow night cheaper` when skipping
  - Shows actual prices in reason: "tomorrow night cheaper (X.XX¢ vs now Y.YY¢)"

## [1.2.7] - 2025-12-08

### Changed
- Day vs tomorrow comparison now looks at tonight's evening window (18:00–00:00) versus tomorrow night's window (00:00–06:00) to avoid skipping an entire day when tomorrow night is cheaper.
- Kept day preheat target while reflecting the new reasoning in status messages.

## [1.2.8] - 2025-12-08

### Fixed
- Resolved startup/import errors by aligning `main.py` with the class-based `PriceAnalyzer`/`Scheduler` flow.
- Removed leftover `dynamic_window_mode` references from configuration and scheduling logic.
- Confirmed single-iteration (`RUN_ONCE`) execution succeeds after the cleanup.

## [1.2.6] - 2025-12-06

### Changed
- **Improved status message when skipping for tomorrow's prices**:
  - Now shows `⏭️ Skipping day heating | Tomorrow night cheaper (€X.XXX)` instead of generic idle message
  - Makes it clear why the scheduled day heating window is being skipped

## [1.2.5] - 2025-12-06

### Added
- **`initial_legionella_date` config option** - Set this once to bootstrap the legionella tracking:
  - Format: `2025-12-06` or `2025-12-06 05:00` or `2025-12-06T05:00:00`
  - Only applies if state has never been set (won't overwrite existing)
  - Clear the setting after first startup

## [1.2.4] - 2025-12-06

### Added
- **Legionella protection tracking** via new `sensor.wh_last_legionella` entity:
  - Shows when legionella protection last ran
  - Shows when next protection is due
  - Indicates if protection is needed now
- **Smart legionella scheduling** - only runs protection cycle if >7 days since last:
  - Prevents running protection twice per day on Saturday
  - Automatically tracks when water reaches 60°C (counts as protection)
  - Persists across add-on restarts

### Fixed
- Fixed issue where legionella protection would run multiple times per day on Saturday

## [1.2.3] - 2025-12-06

### Changed
- **Modularized codebase** for better maintainability:
  - Extracted price analysis logic to `price_analyzer.py`
  - Extracted status management to `status_manager.py`
  - Extracted scheduling logic to `scheduler.py`
  - Created `constants.py` for shared constants
  - Reduced `main.py` to a slim entry point (~170 lines vs ~640 lines)

### Removed
- **Removed `dynamic_window_mode` setting** - this option was defined in configuration but never implemented in code

## [1.2.2] - 2025-12-06

### Changed
- **Improved status messages** with clear context about what's happening and why:
  - 🔥 Active heating shows program type, temperature, and end time
  - ✅ Completion messages when target temp reached
  - ⏳ "Finishing heat cycle" when continuing after window ends
  - 💤 Idle shows next scheduled heating time
  - 🏖️ Away mode status clearly visible
  - 🛁 Bath mode status
  - ⚡ Free energy indicator for negative prices
  - 💰 Low price heating indicator
  - 🦠 Legionella protection status

- **Enhanced logging** for better troubleshooting:
  - Evaluation summary each cycle: `[Day] Idle | €0.220 (Medium) | Window: 06:00-07:00 | Reason`
  - Decision reasoning shows why temperatures were chosen
  - State change logging when heater turns on/off or target changes
  - Legionella optimization only logged when actionable (future window)
  - Heat cycle completion logged with final temperature

## [1.2.1] - 2025-12-05

### Fixed
- **Critical bug fix**: Fixed price level detection using incorrect percentile-based thresholds
  - Bug caused "free energy" mode (70°C heating) to trigger when prices were in the lowest 20% of the day,
    even when prices were 0.23+ EUR/kWh (not actually negative)
  - Now uses fixed price thresholds matching NetDaemon PriceHelper.cs exactly:
    - `None` (70°C): Only when price < 0 (actual negative prices)
    - `Low` (50°C): price < 0.10 EUR/kWh
    - `Medium` (35°C): price < 0.35 EUR/kWh
    - `High` (35°C): price < 0.45 EUR/kWh  
    - `Maximum` (35°C): price >= 0.45 EUR/kWh
- Added debug logging for price level analysis

## [1.2.0] - 2025-12-05

### Changed
- **Major rewrite**: Ported scheduling logic directly from proven NetDaemon WaterHeater.cs implementation
- Simplified time window logic using simple hour-based comparisons instead of complex timezone handling
- Removed complex scheduler.py and price_analyzer.py modules in favor of inline functions
- More reliable heating window detection that matches the original C# behavior

### Fixed
- Fixed issue where heating windows were not being triggered at the scheduled time
- Fixed timezone-related edge cases that caused missed heating slots

## [1.1.6] - 2025-12-03

### Added
- Status sensor now keeps announcing the upcoming heating window once the
	current slot has passed, as soon as the next day's prices are available.

## [1.1.5] - 2025-12-03

### Changed
- Simplified status messages to show current state and next planned heating time (e.g., "Idle, heating at 22:00" or "Heating (58°C)").

## [1.1.4] - 2025-12-03

### Changed
- Updated status icons to seasonal thermometer icons (snowflake-thermometer for winter, water-thermometer for summer) with consistent light blue color.

## [1.1.3] - 2025-12-03

### Changed
- Trimmed schedule status messages so only actionable context (planned window, selected target) appears, removing noisy “no data” fragments.

## [1.1.2] - 2025-12-03

### Changed
- Introduced winter-aware icons/colors for the heating status sensors so the UI reflects the season automatically.

## [1.1.1] - 2025-12-03

- Added entity pickers for water heater, price sensor, and helper switches to prevent typos and make the right sensor selectable

### Fixed
- Corrected the add-on schema definition so Home Assistant recognizes the configuration and the add-on appears in the store

## [1.1.0] - 2025-12-02

### Added
- Rolled schema back to the legacy type definitions (no selectors) to maximize Supervisor compatibility.

## [1.0.0] - 2025-12-02

### Added
- Initial release
- Price-based water heater scheduling
- Temperature presets (eco, comfort, performance, custom)
- Night/Day program logic based on price comparison
- Weekly legionella protection cycle
- Away mode support (optional)
- Bath mode with auto-disable (optional)
- Cycle gap protection to prevent rapid toggling
- Status sensors: `sensor.wh_program`, `sensor.wh_target_temp`, `sensor.wh_status`
- State persistence across container restarts
- MQTT support for entity publishing (when available)
- Local testing via `run_addon.py`
