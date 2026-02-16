---
description: Add a new feature to an existing Home Assistant add-on.
agent: Ask
model: GPT-5.3-Codex
---

Use `Orchestrator` to add a new feature to an existing Home Assistant add-on.

Requirements:
- Read and understand the existing add-on code.
- Determine if OpenSpec proposal is needed (new capability or breaking change).
- Implement the feature following existing patterns.
- Add or update entities as needed.
- Update configuration if new options required.
- Test with existing functionality to ensure no regressions.
- Update documentation and CHANGELOG.

Execution protocol:
1. `Planner` - Define feature scope, affected files, new entities, acceptance criteria.
2. `OpenSpec Manager` - Create proposal if new capability or breaking change.
3. `Python Developer` - Implement feature in existing add-on structure.
4. `Shared Module Manager` - Sync if shared modules modified.
5. `Tester` - Validate feature works, no regressions in existing functionality.
6. `Reviewer` - Check code quality, consistency with existing code.
7. `Docs Writer` - Update README, add CHANGELOG entry.
8. `Add-on Packager` - Bump version, update config.yaml if needed.
9. `OpenSpec Manager` - Archive proposal if created.

Respond with:
1) Feature implemented: [description]
2) Add-on affected: [name]
3) New/modified entities: [list]
4) Configuration changes: [list]
5) Test results: [pass/fail]
6) Version bump: [X.Y.Z]
7) Files changed: [list]
