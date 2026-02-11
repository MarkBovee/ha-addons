---
applyTo: '**'
---

# Documentation Standards

Rules for creating and maintaining documentation in this repository.

---

## Core Principles

1. **Single Source of Truth** - One comprehensive README per project/module + canonical specs in `openspec/specs/`
2. **Always Up-to-Date** - Update documentation with every related code change
3. **No Temporary Files** - Never create report, summary, or status files (see below)

---

## Documentation Hierarchy

| Location | Purpose | Examples |
|----------|---------|---------|
| `README.md` (root) | Project overview, installation, add-on list, development guide | Add-on descriptions, quick start |
| `<addon>/README.md` | Add-on-specific docs, config options, usage | Energy Prices templates, Battery Manager thresholds |
| `openspec/specs/` | Canonical specifications per capability | `specs/energy-prices/spec.md` |
| `openspec/changes/` | Change proposals (temporary until archived) | `changes/add-solar-bonus/proposal.md` |
| `docs/` | Deep-dive guides only (>100 lines, complex topics) | Architecture details, integration guides |

---

## Prohibited Files

**Never create these files anywhere in the repo:**

- `*_REPORT.md`, `*_SUMMARY.md`, `*_COMPLETE.md`
- `PROGRESS_*.md`, `PHASE_*.md`, `*_GUIDE.md` (unless permanent in `/docs/`)
- Any file documenting "what was done" or "current status"

**Where information belongs instead:**

| Information | Correct Location |
|-------------|-----------------|
| What the project does | `README.md` |
| Current requirements | `openspec/specs/[capability]/spec.md` |
| Why we're changing something | `openspec/changes/[id]/proposal.md` |
| Task progress | Checkmarks in `tasks.md` (`[x]` done, `[-]` in progress) |
| Historical information | Git commit messages |

---

## OpenSpec Change Folder Structure

Strict. Only these files are allowed:

```
openspec/changes/[change-id]/
+-- proposal.md       # REQUIRED - Why, what, impact
+-- tasks.md          # REQUIRED - Implementation checklist
+-- design.md         # OPTIONAL - Complex technical decisions only
+-- specs/            # REQUIRED - Delta specifications
    +-- [capability]/
        +-- spec.md   # ADDED/MODIFIED/REMOVED requirements
```

---

## README Standards

Every add-on README should include:
- What it does and why
- Installation steps
- Configuration options (matching `config.yaml` schema)
- Entity list with descriptions
- Dependencies on other add-ons (if any)

Root README should include:
- Repository purpose and installation
- List of all available add-ons
- Development instructions (`run_addon.py`, shared modules)

---

## When Code Changes, Update Docs

- **New feature:** Update README, add to CHANGELOG
- **New config option:** Update `config.yaml` schema AND README
- **Renamed/removed entity:** Update README entity list
- **New add-on:** Update root README add-on list and `repository.json`
- **Shared module change:** Note impact in commit message

---

## Spec Writing Format

Use SHALL/MUST language with testable scenarios:

```markdown
### Requirement: Feature Name
The system SHALL [behavior statement].

#### Scenario: Success case
- **WHEN** [trigger]
- **THEN** [expected result]
- **AND** [additional validation]
```

For spec deltas in change proposals, use `## ADDED`, `## MODIFIED`, or `## REMOVED Requirements` headers. Check `openspec/specs/` first to determine which header to use.
