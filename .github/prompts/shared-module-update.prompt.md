---
description: Update shared modules and sync across all Home Assistant add-ons with regression testing.
agent: Ask
model: GPT-5.3-Codex
---

Use `Orchestrator` with `Shared Module Manager` to update shared modules safely.

Requirements:
- Ensure changes are made to root `shared/` directory (not `<addon>/shared/`).
- Sync to all add-ons.
- Run regression testing on all add-ons to ensure no breakage.

Execution protocol:
1. `Planner` - Define scope: which shared module(s), what changes, why needed.
2. `Python Developer` - Implement changes in root `shared/` directory only.
3. `Shared Module Manager` - Validate edit location, sync to all add-ons, verify consistency.
4. `Tester` - Run regression testing on ALL add-ons:
   - battery-api
   - battery-manager
   - charge-amps-monitor
   - energy-prices
   - water-heater-scheduler
5. `Reviewer` - Check changes follow shared module best practices.
6. `Docs Writer` - Update root README if module functionality changes significantly.

Critical validation gates:
- [ ] Changes are in root `shared/` (not in any `<addon>/shared/`)
- [ ] `sync_shared.py` executed successfully
- [ ] All add-on `shared/` directories match root
- [ ] All add-ons tested and pass
- [ ] No regression issues introduced

Respond with:
1) Shared module(s) modified: [list]
2) Changes made: [description]
3) Sync status: [success/failure]
4) Add-ons tested: [list with pass/fail per add-on]
5) Regression issues: [none or list issues found]
6) Files changed: [root shared/ files]
