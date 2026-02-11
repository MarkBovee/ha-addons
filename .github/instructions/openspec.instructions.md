---
applyTo: 'openspec/**'
---

# OpenSpec Usage

Rules for using OpenSpec in this repository. For full CLI reference, see `openspec/AGENTS.md`.

---

## When to Create a Change Proposal

**Create a proposal for:**
- New features or capabilities
- Breaking changes (API, schema, entity names)
- Architecture changes

**Skip proposal for:**
- Bug fixes, typos, formatting
- Non-breaking dependency updates
- Config changes, test additions

---

## Creating a Change

1. Check existing state: `openspec list` and `openspec list --specs`
2. Choose a verb-led change ID: `add-solar-bonus`, `update-price-calc`, `remove-legacy-api`
3. Scaffold the change folder:

```
openspec/changes/[change-id]/
+-- proposal.md       # Why, what, impact (REQUIRED)
+-- tasks.md          # Implementation checklist (REQUIRED)
+-- design.md         # Technical decisions (OPTIONAL - only if complex)
+-- specs/            # Delta specifications (REQUIRED)
    +-- [capability]/
        +-- spec.md
```

4. Write spec deltas using correct headers:
   - Spec does NOT exist in `openspec/specs/` -> use `## ADDED Requirements`
   - Spec already exists in `openspec/specs/` -> use `## MODIFIED Requirements` or `## REMOVED Requirements`
5. Validate: `openspec validate [change-id] --strict`

---

## Spec Delta Format

```markdown
# Delta: [Capability] Specification

## ADDED Requirements

### Requirement: Feature Name
The system SHALL [behavior].

#### Scenario: Success case
- **WHEN** [trigger]
- **THEN** [expected result]

## MODIFIED Requirements

### Requirement: Existing Feature
The system SHALL [updated behavior].

#### Scenario: Updated case
- **WHEN** [trigger]
- **THEN** [new expected result]

## REMOVED Requirements

### Requirement: Old Feature
**Reason**: [Why removing]
```

Every requirement MUST have at least one `#### Scenario:` (use exactly 4 `#`).

---

## Proposal.md Template

```markdown
## Why
[1-2 sentences on problem/opportunity]

## What Changes
- [Bullet list of changes]
- [Mark breaking changes with **BREAKING**]

## Impact
- Affected specs: [list capabilities]
- Affected code: [key files/systems]
```

---

## Tasks.md Format

```markdown
## 1. Phase Name
- [ ] 1.1 Task description
- [ ] 1.2 Another task
- [-] 1.3 In-progress task
- [x] 1.4 Completed task
```

Update checkmarks as work progresses. Keep `proposal.md` status in sync.

---

## Implementing Changes

1. Read `proposal.md` and `tasks.md`
2. Read `design.md` if it exists
3. Implement tasks sequentially
4. Mark tasks `[x]` as completed
5. Verify all tasks complete before closing

---

## After Deployment

Archive completed changes: `openspec archive [change-id] --yes`

This moves the change to `changes/archive/` and merges spec deltas into `openspec/specs/`.

---

## CLI Quick Reference

```bash
openspec list                       # Active changes
openspec list --specs               # Existing specifications
openspec show [item]                # View change or spec
openspec validate [id] --strict     # Validate before archiving
openspec archive [id] --yes         # Archive after deployment
```

---

## Common Mistakes

- Using `## MODIFIED` on a spec that doesn't exist yet (use `## ADDED`)
- Missing `#### Scenario:` for a requirement (use 4 `#`, not 3)
- Adding extra files to change folders (only `proposal.md`, `tasks.md`, `design.md`, `specs/`)
- Forgetting to check `openspec/specs/` before choosing ADDED vs MODIFIED
