# Implementation Tasks

## Phase 1: Configuration & Dependencies
- [x] 1.1 Add `astral` to requirements.txt
- [x] 1.2 Update `config.yaml` with new options (bonus, location)
- [x] 1.3 Update `EP_CONFIG_DEFAULTS` in `main.py`

## Phase 2: Core Logic
- [x] 2.1 Implement `is_daylight` helper using `astral`
- [x] 2.2 Implement `calculate_import_price` with new formula
- [x] 2.3 Implement `calculate_export_price` with Zonneplan logic
- [x] 2.4 Update `fetch_and_process_prices` to use new logic

## Phase 3: Refactoring
- [x] 3.1 Move solar bonus logic to `app/solar_bonus.py`
- [x] 3.2 Update `main.py` to import from `solar_bonus.py`

## Phase 4: Verification
- [x] 4.1 Verify import formula
- [x] 4.2 Verify export logic (day/night, positive/negative)
- [x] 4.3 Verify logging updates
