---
description: Complete development and testing cycle for Home Assistant add-on changes.
agent: Ask
model: GPT-5.3-Codex
---

Use `Orchestrator` for full development lifecycle from planning to release-ready state.

Requirements:
- Clear definition of what needs to be built or changed.
- Local testing environment set up (run_addon.py, .env files).
- All quality gates passed before completion.

Execution protocol:
1. `Planner` - Comprehensive plan with tasks, acceptance criteria, risks.
2. `OpenSpec Manager` - Create proposal if new capability or breaking change.
3. `Python Developer` - Implement changes following repository conventions.
4. `Shared Module Manager` - Sync if shared modules affected.
5. `Tester` - Validate functionality, run regression tests.
6. `Reviewer` - Code quality review, must-fix issues identified.
7. If review fails → Loop: `Python Developer` → `Tester` → `Reviewer` until approved.
8. `Docs Writer` - Update documentation, CHANGELOG.
9. `Add-on Packager` - Validate packaging, bump version, finalize release artifacts.
10. `OpenSpec Manager` - Archive proposal if created.

Mandatory delivery gates:
- [ ] Planning includes explicit acceptance criteria
- [ ] OpenSpec proposal created and validated (if required)
- [ ] All tests pass with commands documented
- [ ] Code review approved (no must-fix issues)
- [ ] Documentation updated
- [ ] CHANGELOG entry added
- [ ] Version bumped correctly
- [ ] Packaging validated (Dockerfile, config.yaml, requirements.txt)

Respond with:
1) What changed: [summary]
2) Add-on(s) affected: [list]
3) New/modified entities: [list]
4) Configuration changes: [list]
5) Test results: [pass/fail with commands]
6) Review status: [approved/changes requested]
7) Version: [X.Y.Z]
8) Files changed: [list]
9) Release readiness: [Go/No-Go with open risks if any]
