---
applyTo: '**'
---

# Agent Workflow

Rules for AI assistants working in this repository. Follow these steps for every task.

---

## Step 0: Branch First

**Never work on `master` directly.** Before writing any code:

| Change Type | Branch Pattern | Example |
|-------------|---------------|---------|
| New feature / breaking change | `feature/[name]` | `feature/add-solar-forecast` |
| Bug fix | `fix/[name]` | `fix/grace-period-calculation` |
| Refactor | `refactor/[name]` | `refactor/price-calc` |
| Documentation | `docs/[name]` | `docs/update-readme` |

If a related branch already exists, reuse it.

**New features and breaking changes** also require an OpenSpec change proposal - see `openspec.instructions.md`.

---

## Step 1: Understand Before Changing

- Read the files you plan to modify
- Check `openspec/specs/` for related specifications
- Check `openspec/changes/` for in-flight proposals that might conflict
- If requirements are ambiguous, ask the user before proceeding

---

## Step 2: Plan (for non-trivial work)

For multi-step tasks:
1. Define what done looks like (testable success criteria)
2. Identify risks and dependencies
3. Break work into concrete tasks
4. For OpenSpec changes: create `proposal.md` and `tasks.md`

Skip formal planning for single-file bug fixes, typos, or simple config changes.

---

## Subagent Performance Policy

Use subagents selectively to avoid latency and timeout issues.

- Prefer **direct local execution first** (workspace search, file reads, terminal/API calls)
	for bug fixes, log analysis, and targeted refactors.
- Use subagents only when work is truly parallel or the user explicitly asks for a
	specialized agent flow.
- If a subagent call is slow or times out once, fall back to direct execution instead
	of retrying the same delegation pattern.
- For Home Assistant diagnostics, query the HA API and local repo directly before
	escalating to multi-agent orchestration.

---

## Step 3: Implement

- Follow coding standards in `coding.instructions.md`
- Write complete, working code - no placeholders or TODOs
- Build and test as you go
- For OpenSpec changes: update `tasks.md` progress as you complete tasks

---

## Step 4: Verify

- [ ] Code compiles / runs without errors
- [ ] All existing tests still pass
- [ ] New functionality is tested
- [ ] For OpenSpec changes: `openspec validate [change-id] --strict` passes

---

## Step 5: Document

Before committing, update documentation affected by your changes:

- [ ] `README.md` (root or addon-level) if user-facing behavior changed
- [ ] `config.yaml` if new options were added
- [ ] `CHANGELOG.md` for the affected addon
- [ ] For OpenSpec changes: update `proposal.md` status and `tasks.md` checkboxes
- [ ] Verify no temporary report files exist (see `documentation.instructions.md`)

---

## Step 6: Commit

Use conventional commit messages:

```
feat(energy-prices): add solar bonus calculation
fix(battery-manager): prevent rapid charge cycling
docs(readme): update addon list with battery-api
refactor(shared): extract MQTT retry logic
```

Include what changed and why. Reference issues or OpenSpec changes when relevant.

---

## File Rules

**Never create these files:**
- `*_REPORT.md`, `*_SUMMARY.md`, `*_COMPLETE.md`, `PROGRESS_*.md`, `PHASE_*.md`
- Progress goes in `tasks.md` checkboxes; status goes in `proposal.md`; history goes in git commits

**OpenSpec change folders may only contain:**
- `proposal.md` (required), `tasks.md` (required), `design.md` (optional), `specs/` (required)

---

## Commit Checklist (Quick Reference)

- [ ] On a non-master branch
- [ ] Code works and tests pass
- [ ] Documentation updated
- [ ] No temporary/report files created
- [ ] Commit message follows `type(scope): description` format
