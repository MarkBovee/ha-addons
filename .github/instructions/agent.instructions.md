---
applyTo: '**'
---

# Agent Workflow (Lean)

Use this workflow for all tasks in this repository.

## 1) Branch Safety

- Never work on `master`.
- Use branch patterns:
  - Feature: `feature/[name]`
  - Bug fix: `fix/[name]`
  - Refactor: `refactor/[name]`
  - Docs: `docs/[name]`

## 2) Direct-First Execution

- `Orchestrator` handles work directly by default.
- Delegate only when specialized help is required or parallel lanes clearly save time.
- If a delegated lane is slow, fall back to direct execution.

## 3) Keep It Tight

- Read only files needed for the task.
- Make minimal, focused edits.
- Do not add progress/report files.

## 4) Plan Only When Needed

Create a formal plan for non-trivial, multi-step work. For simple fixes, execute directly.

## 5) Verify

- Run targeted validation first, then broader checks if needed.
- Report what was run and the outcome.

## 6) Document Impact

When behavior/config/version changes:

- Update add-on `README.md` if user-facing behavior changed.
- Update `config.yaml` if options changed.
- Update add-on `CHANGELOG.md` where applicable.

## 7) OpenSpec Rule

OpenSpec proposal required for new capabilities and breaking changes.
Skip OpenSpec for bug fixes, typos, formatting, and non-breaking maintenance.