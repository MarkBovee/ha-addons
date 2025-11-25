# Tasks - Universal Add-on Runner (Version 1.1)

## Status
🟡 IN PROGRESS - 0%

## Phase 1: Scaffold & Branch
- [x] 1.1 Create branch `feature/universal-addon-runner` - **DONE [2025-11-25]**
- [x] 1.2 Create OpenSpec change folder with `proposal.md` & `tasks.md` - **DONE [2025-11-25]**

## Phase 2: Core Runner Implementation
- [ ] 2.1 Implement `run_addon.py` with addon discovery
- [ ] 2.2 Implement layered env loading and token normalization
- [ ] 2.3 Add per-add-on env validation and execution of `run_local.py`

## Phase 3: Cross-Platform Wrapper Scripts
- [ ] 3.1 Add `run_addon.ps1` for Windows PowerShell
- [ ] 3.2 Add `run_addon.sh` for Unix shells

## Phase 4: Documentation
- [ ] 4.1 Update root `README.md` with runner usage and `.env.<slug>` convention
- [ ] 4.2 Add `.env.charge-amps-monitor.example`

## Phase 5: Enhancements (Optional)
- [ ] 5.1 Add `--dry-run` and `--list` CLI options
- [ ] 5.2 Add `--venv` placeholder for future isolation
- [ ] 5.3 Add HA URL override note for add-ons
