---
description: Emulate Claude-style agent teams using Orchestrator with parallel specialist lanes and quality gates.
agent: Ask
model: GPT-5.3-Codex
---

Use `Orchestrator` in team-emulation mode for complex Home Assistant add-on development.

Execution protocol:
1) Build shared todo list with lane ownership in each task title (for example: `[Python Developer]`, `[Tester]`).
2) Keep `Orchestrator` coordination-only while delegated lanes are active.
3) Run independent lanes in parallel using subagents; keep dependent tasks sequential.
4) Require each lane to return: decisions, files changed, risks, next actions.
5) Merge lane outputs and resolve conflicts before validation.
6) Enforce quality gates:
   - `Tester` pass/fail with commands
   - `Reviewer` must-fix findings
   - `Shared Module Manager` sync validation (if applicable)
   - `Add-on Packager` release artifact validation
7) If gates fail, run fix loop: `Python Developer` → `Tester` → `Reviewer`.
8) Finish with release readiness summary and open risks.

Lane specialization for HA add-ons:
- **Planning lane**: `Planner`, `OpenSpec Manager`
- **Implementation lane**: `Python Developer`, `Shared Module Manager`
- **Validation lane**: `Tester`, `HA Debugger` (if needed)
- **Quality lane**: `Reviewer`
- **Release lane**: `Docs Writer`, `Add-on Packager`

Parallel execution strategy:
- Planning and OpenSpec proposal creation can run in parallel with existing code analysis.
- Implementation and documentation can run in parallel if clear handoff contract defined.
- Testing and review are sequential (test first, then review).

Output format:
- Team lanes used: [list]
- Tasks completed by lane: [breakdown]
- Files changed: [list]
- Entities created/modified: [list]
- Validation results: [pass/fail per gate]
- Release readiness: [Go/No-Go]
- Open risks: [list or "none"]
