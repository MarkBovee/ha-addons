---
description: Fast-track bug fix flow for Home Assistant add-ons.
agent: Ask
model: GPT-5.3-Codex
---

Use `Orchestrator` for quick bug fix with minimal overhead.

Requirements:
- Identify the bug and affected add-on.
- Reproduce the issue locally if possible.
- Implement minimal fix without over-engineering.
- Validate fix resolves issue without breaking existing functionality.
- Update CHANGELOG with fix description.

Execution protocol (streamlined):
1. `Planner` - Quick scope: what's broken, expected vs actual behavior, fix approach.
2. `Python Developer` - Implement minimal fix, add error handling if missing.
3. `Tester` - Verify fix works, regression check existing features.
4. `Reviewer` - Quick review: fix is minimal, no side effects.
5. `Docs Writer` - Add CHANGELOG entry (bug fix section).
6. `Add-on Packager` - Bump PATCH version.

Optional (if needed):
- `HA Debugger` - If issue requires live HA instance diagnosis (sensors, logs, MQTT).
- `Shared Module Manager` - If bug is in shared module (sync required).

Respond with:
1) Bug: [description]
2) Root cause: [technical explanation]
3) Fix applied: [changes made]
4) Test results: [pass/fail]
5) Version bump: [X.Y.Z]
6) Files changed: [list]
