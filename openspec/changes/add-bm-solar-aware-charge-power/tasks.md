## 1. OpenSpec Scope
- [x] 1.1 Add delta requirements for forecast-assisted charge power allocation
- [x] 1.2 Validate change with `openspec validate add-bm-solar-aware-charge-power --strict`

## 2. Runtime Logic
- [x] 2.1 Add helper logic to parse remaining solar energy and calculate remaining charge deficit
- [x] 2.2 Allocate per-slot charge power for today's remaining charge windows using rolling recalculation
- [x] 2.3 Fall back to existing ranked charge power when solar forecast is unavailable or disabled

## 3. Config and Visibility
- [x] 3.1 Add remaining solar entity and solar-aware charging options to `battery-manager/config.yaml`
- [x] 3.2 Expose solar-aware charge context in schedule/current-action attributes and logs
- [x] 3.3 Update `battery-manager/README.md` and `battery-manager/CHANGELOG.md`

## 4. Verification
- [x] 4.1 Add unit tests for solar-aware charge allocation helpers
- [x] 4.2 Add schedule-generation regressions for reduced charge power and fallback behavior
- [x] 4.3 Run targeted pytest for changed battery-manager modules