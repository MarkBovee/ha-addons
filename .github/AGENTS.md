# Lean Agent Team (Home Assistant Add-ons)

This repository uses a **direct-first** agent setup.

## Core Principle

- `Orchestrator` does most work alone by default.
- Delegate only when work is clearly specialized or parallelizable.
- Prefer fast completion over process overhead.

## Team Roles

- `Orchestrator` - Default owner for end-to-end delivery
- `Python Developer` - Complex implementation help
- `HA Debugger` - Live Home Assistant diagnostics
- `Tester` - Validation and regression checks
- `Reviewer` - Focused code quality review
- `Planner` - Structured plan for larger features
- `Docs Writer` - README/CHANGELOG/config documentation updates
- `Add-on Packager` - Docker/config/version/release updates
- `Shared Module Manager` - Root `shared/` changes and sync workflow
- `OpenSpec Manager` - OpenSpec proposals for new capabilities/breaking changes

## Operating Mode

1. Start with `Orchestrator` in direct execution mode.
2. Delegate only if one of these is true:
   - Domain-specialist input is required (HA live debugging, packaging, OpenSpec).
   - Parallel lanes can reduce wall-clock time.
   - Independent review/testing can run concurrently.
3. Merge results in `Orchestrator`, then provide one final answer.

## Parallel Rule

- Run independent tasks in parallel.
- Keep dependent tasks sequential (implement -> test -> review).

## Quality Gates

- Non-master branch.
- Required tests/validation run and reported.
- OpenSpec proposal for new capabilities or breaking changes.
- Docs updated when behavior/config changes.

## Structure

- Agents: `.github/agents/*.agent.md`
- Prompt shortcuts: `.github/prompts/*.prompt.md`
- Workflow and repo rules: `.github/instructions/*.instructions.md`
