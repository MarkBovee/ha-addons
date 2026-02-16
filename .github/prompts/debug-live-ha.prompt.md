---
description: Debug live Home Assistant issues using HA Debugger to collect diagnostic data.
agent: Ask
model: GPT-5.3-Codex
---

Use `Orchestrator` with `HA Debugger` to diagnose live HA instance issues.

Requirements:
- Access to Home Assistant instance (Supervisor API, MQTT broker if applicable).
- Environment variables: SUPERVISOR_TOKEN, HA_URL, MQTT credentials (if needed).
- Clear description of the symptom or issue.

Execution protocol:
1. `Planner` - Define symptom, affected add-on, entities involved, expected vs actual behavior.
2. `HA Debugger` - Connect to HA and collect diagnostics:
   - Entity states and attributes
   - Add-on logs (last 100-500 lines)
   - MQTT messages (if applicable)
   - API responses (if external API involved)
   - Configuration validation
3. `HA Debugger` - Analyze root cause from collected data.
4. `Python Developer` - Implement fix if code change needed.
5. `Tester` - Validate fix in local environment.
6. `HA Debugger` - Verify fix in live HA instance.

Optional follow-up:
- `Reviewer` - If significant code changes made.
- `Docs Writer` - If fix reveals documentation gap.
- `Add-on Packager` - Bump version and update CHANGELOG.

Respond with:
1) Symptom: [user-reported issue]
2) Diagnostic data collected:
   - Entity states: [values]
   - Logs excerpt: [relevant lines]
   - MQTT messages: [if applicable]
3) Root cause: [technical explanation]
4) Fix recommendation: [code changes or config adjustments]
5) Verification: [how to confirm fix worked]
