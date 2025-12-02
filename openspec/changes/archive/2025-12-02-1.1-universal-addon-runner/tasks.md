# Tasks - Universal Add-on Runner (Version 1.1)

## Status
✅ COMPLETE - 100%

## Phase 1: Scaffold & Branch
- [x] 1.1 Create branch `feature/universal-addon-runner` - **DONE [2025-11-25]**
- [x] 1.2 Create OpenSpec change folder with `proposal.md` & `tasks.md` - **DONE [2025-11-25]**

## Phase 2: Core Runner Implementation
- [x] 2.1 Implement `run_addon.py` with addon discovery - **DONE**
- [x] 2.2 Implement layered env loading and token normalization - **DONE**
- [x] 2.3 Add per-add-on env validation and execution of `run_local.py` - **DONE**

## Phase 3: Cross-Platform Wrapper Scripts
- [x] 3.1 Add `run_addon.ps1` for Windows PowerShell - **DONE**
- [x] 3.2 Add `run_addon.sh` for Unix shells - **SKIPPED** (Python script works directly)

## Phase 4: Documentation
- [x] 4.1 Update root `README.md` with runner usage and `.env.<slug>` convention - **DONE**
- [x] 4.2 Add `.env.charge-amps-monitor.example` - **DONE** (as `.env.example` per addon)

## Phase 5: Enhancements (Optional)
- [x] 5.1 Add `--dry-run` and `--list` CLI options - **DONE**
- [x] 5.2 Add `--venv` placeholder for future isolation - **SKIPPED** (not needed yet)
- [x] 5.3 Add HA URL override note for add-ons - **SKIPPED** (documented elsewhere)
