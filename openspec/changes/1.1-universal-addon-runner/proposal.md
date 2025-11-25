# Universal Add-on Runner Proposal

Version: 1.1
Status: 🟡 IN PROGRESS
Last Updated: 2025-11-25

## Executive Summary
Introduce a universal local runner script at the repository root to run any add-on against a local or remote Home Assistant instance. The runner standardizes environment loading, token normalization, validation, and execution, enabling faster integration testing across all add-ons.

## What's Changing
| Area | Before | After |
|---|---|---|
| Local running | Per-add-on scripts only | Root `run_addon.py` selects add-on |
| Env files | Ad-hoc `.env` in addon | Root-level `.env.<slug>` convention |
| HA tokens | Inconsistent (`HA_API_TOKEN` vs `SUPERVISOR_TOKEN`) | Normalized: both set if one provided |
| Validation | Script-specific | Centralized per-add-on validation in runner |

## Benefits
- Consistent developer experience across add-ons
- Reduced duplication of run scripts
- Clear environment and token handling
- Future extensibility for tests/lint/health checks

## Success Criteria
- `python run_addon.py --list` shows available add-ons
- `python run_addon.py --addon charge-amps-monitor` launches locally when required env vars are provided
- Env token normalization sets both `SUPERVISOR_TOKEN` and `HA_API_TOKEN`
- Per-add-on missing env vars produce clear error messages

## Risks & Mitigations
- Different Python dependencies per add-on → Mitigate by running existing `run_local.py` within the add-on directory and deferring virtual env management.
- Hardcoded HA URLs in some add-ons → Mitigate by later patch to allow `HA_API_URL` override.

## Timeline
- Day 0: Implement runner and wrappers, add minimal docs
- Day 1+: Optional patch add-ons for HA URL override, add venv support
