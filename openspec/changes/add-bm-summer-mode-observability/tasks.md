## 1. OpenSpec Scope
- [ ] 1.1 Confirm capability scope as informational-only (no scheduling behavior change)
- [ ] 1.2 Validate change with `openspec validate add-bm-summer-mode-observability --strict`

## 2. Detection Logic
- [ ] 2.1 Add summer-mode detector in `battery-manager/app/price_analyzer.py`
- [ ] 2.2 Use today-only price points and robust timestamp parsing
- [ ] 2.3 Apply majority-of-top-N check in noon window (default 10:00-16:00)

## 3. Runtime Integration
- [ ] 3.1 Compute and persist summer-mode in runtime state during schedule generation
- [ ] 3.2 Expose summer-mode in existing mode/reasoning/status attributes
- [ ] 3.3 Add one-time-per-day summer day-start banner to schedule output

## 4. Config and Docs
- [ ] 4.1 Add `heuristics.summer_mode_*` options to `battery-manager/config.yaml`
- [ ] 4.2 Update `battery-manager/README.md` with behavior and options
- [ ] 4.3 Add release note to `battery-manager/CHANGELOG.md`

## 5. Verification
- [ ] 5.1 Add unit tests for summer-mode detection scenarios
- [ ] 5.2 Add tests for day-start banner and summer visibility output
- [ ] 5.3 Run targeted pytest subset for changed modules
