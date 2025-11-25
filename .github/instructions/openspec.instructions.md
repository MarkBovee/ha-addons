---
applyTo: 'openspec/**'
---

# 📋 OpenSpec Progress Tracking Automation

This guide automates OpenSpec status tracking for features across all phases.

---

## Overview

When implementing any OpenSpec feature (1.x, 2.x, etc.), maintain synchronized progress across:
1. **proposal.md** - Executive status
2. **tasks.md** - Detailed task tracking  
3. **STATUS.md** - Comprehensive report (optional for complex features)
4. **spec.md** - Requirements (no changes once locked)

---

## Automatic Progress Tracking Pattern

### When to Update

Update OpenSpec files at these trigger points:

| Trigger | Update File | What to Change |
|---------|------------|-----------------|
| Feature starts | proposal.md | Status: PENDING → IN PROGRESS |
| Feature starts | tasks.md | Mark first phase as `in-progress` |
| Phase completes | tasks.md | Mark phase tasks as `[x]` with timestamp |
| Phase starts | tasks.md | Add phase status (✅, 🟡, ⏳) markers |
| Milestone reached | proposal.md | Update progress percentage |
| Session ends | STATUS.md | Create/update comprehensive report |

---

## Update Patterns by File

### proposal.md - Status Field

**Pattern: Status Line Update**

```markdown
**Status:** [Old Status]
```

**Should Become:**

```markdown
**Status:** 🟡 **IN PROGRESS - [X]% COMPLETE**
```

**Update at these milestones:**
- 0% → 10%: First phase started
- 10% → 25%: First quarter complete
- 25% → 50%: Halfway done
- 50% → 75%: Third quarter complete
- 75% → 90%: Nearly complete
- 90% → 100%: Ready to merge

---

### tasks.md - Task Markers

**Pattern: Task Completion Markers**

**Not Started:**
```markdown
- [ ] Task description
```

**Ready to Execute:**
```markdown
- [ ] Task description - **Phase X: Ready**
```

**In Progress:**
```markdown
- [-] Task description - **Phase X: In Progress**
```

**Completed:**
```markdown
- [x] Task description - **DONE [timestamp]**
```

**Phase Status Summary (at end of file):**
```markdown
## Overall Progress

**✅ COMPLETE (X of Y phases):**
- Phase 1: Description - 100% ✓

**🟡 READY TO EXECUTE (X of Y phases):**
- Phase 2: Description - Ready

**⏳ PENDING (X of Y phases):**
- Phase 3: Description - Waiting

**Status:** X% Complete | On Schedule
```

---

### STATUS.md - Comprehensive Report

**When to Create:**
- When feature reaches 25% completion
- When feature reaches 50% completion  
- At each phase boundary
- When status is complex or multi-threaded

**Template Structure:**

```markdown
# 🚀 Feature [ID] - Implementation Status Update

**Date:** [Date]  
**Time:** [Time]  
**Overall Progress:** X% Complete (Y of Z phases)

---

## ✅ What's Complete

### Phase [N]: [Description] ✅ COMPLETE
- **What:** [What was done]
- **Result:** ✅ SUCCESS
- **Details:** [Key accomplishments]
- **Duration:** [Time taken]

---

## 🟡 What's Ready Next

### Phase [N]: [Description] 🟡 READY
- **Task:** [What needs doing]
- **Command:** [Exact command to run]
- **Expected Outcome:** [What should happen]
- **Success Criteria:** [How to validate]

---

## ⏳ Not Started

### Phase [N]: [Description] ⏳ PENDING
- **Tasks:** [What needs doing]
- **Estimated Duration:** [Time estimate]

---

## 📊 Statistics

[Table of metrics]

---

## 🔗 Dependencies

**Completed:** [List]
**Unblocked:** [List]
**Downstream:** [List]

---

## ✨ Summary

**What We've Accomplished:** [List]
**Current State:** [Status]
**Remaining Work:** [Timeline]
```

---

## Automation Rules for Agents

### Rule 1: Always Update on Phase Completion
**Trigger:** Phase work finished
**Action:** 
1. Mark all completed tasks as `[x]` in tasks.md
2. Update phase percentage in proposal.md
3. Update phase status in tasks.md summary

**Example:**
```
If Phase 1 complete:
  tasks.md: Phase 1 → "## Overall Progress: ✅ COMPLETE (1 of 6)"
  proposal.md: Status → "🟡 IN PROGRESS - 17% COMPLETE"
```

### Rule 2: Always Update on Phase Start
**Trigger:** Beginning Phase N
**Action:**
1. Mark phase heading with 🟡 READY or 🟡 IN PROGRESS
2. Mark first task as `[-]` (in-progress)
3. Add note: "**Phase X: In Progress**"

### Rule 3: Maintain Consistent Markers
**Use These Markers Consistently:**
- ✅ = Complete/Success/Passed
- 🟡 = In Progress/Ready/Pending
- ⏳ = Not Started/Blocked/Waiting
- ❌ = Failed/Issue
- ⚠ = Warning/Caution

### Rule 4: Always Link to Specifications
**Every proposal.md should include:**
```markdown
**Specifications:**
- Proposal: `openspec/changes/[ID]/proposal.md` ✓
- Tasks: `openspec/changes/[ID]/tasks.md` ✓
- Spec: `openspec/changes/[ID]/specs/*/spec.md` ✓
```

### Rule 5: Track Time at Phase Boundaries
**When completing each phase, record:**
```markdown
- Phase [N]: [Description] ✅ COMPLETE
  - Duration: [Time taken]
  - Completed: [HH:MM AM/PM]
  - Issues: [None/Brief list]
```

---

## Quick Reference: Update Checklist

**When starting a feature:**
- [ ] Create proposal.md with status `PENDING APPROVAL` or `IN PROGRESS`
- [ ] Create tasks.md with all tasks listed
- [ ] Create spec.md with requirements
- [ ] Link all files in proposal.md

**At phase completion:**
- [ ] Mark all tasks in tasks.md as `[x]`
- [ ] Add completion time/date
- [ ] Update phase percentage in proposal.md
- [ ] Update overall progress summary in tasks.md

**At feature completion:**
- [ ] Update proposal.md status to `APPROVED` or `COMPLETE`
- [ ] Archive any STATUS.md files
- [ ] Create completion report (optional)
- [ ] Mark all remaining tasks as `[x]`

---

## Examples by Feature Phase Count

### For 2-Phase Features
**Phase 1 Complete:**
- proposal.md: 50% → `🟡 IN PROGRESS - 50% COMPLETE`
- tasks.md: Summary → `✅ COMPLETE (1 of 2)`

**Both Complete:**
- proposal.md: 100% → `✅ APPROVED`
- tasks.md: Summary → `✅ COMPLETE (2 of 2)`

### For 6-Phase Features (Like 1.3.1)
**Phase 1 Complete:**
- proposal.md: 17% → `🟡 IN PROGRESS - 17% COMPLETE`
- tasks.md: Summary → `✅ COMPLETE (1 of 6)`

**Phase 2 Complete:**
- proposal.md: 33% → `🟡 IN PROGRESS - 33% COMPLETE`
- tasks.md: Summary → `✅ COMPLETE (2 of 6) | 🟡 READY TO EXECUTE (4 of 6)`

**Phase 3 Complete:**
- proposal.md: 50% → `🟡 IN PROGRESS - 50% COMPLETE`
- tasks.md: Summary → `✅ COMPLETE (3 of 6) | 🟡 READY (3 of 6)`

---

## File Synchronization Rules

**These MUST always stay in sync:**

| proposal.md | tasks.md | Meaning |
|------------|----------|---------|
| 0% | All [ ] | Not started |
| 0-25% | First phase [ ] | Planning/setup |
| 25-50% | First 1-2 phases [x] | Initial phases done |
| 50-75% | Half phases [x] | Halfway through |
| 75-99% | Most [x], few [ ] | Nearly complete |
| 100% | All [x] | Done |

**Sync Check:** If proposal.md says "50%" but tasks.md shows "25%", fix synchronization.

---

## Common Mistakes to Avoid

❌ **DO NOT:**
- Leave proposal.md status stale while tasks.md is updated
- Update tasks.md without updating proposal.md
- Use different percentage calculations
- Forget to timestamp completions
- Mark tasks complete without verifying they work
- Leave in-progress markers after phase completes

✅ **DO:**
- Update both files together
- Use consistent math (phases: 1/N, not percentages)
- Add timestamps to completions
- Verify before marking complete
- Clean up markers after phase done
- Sync files at phase boundaries

---

## Integration with Session Management

**Session Start:**
1. Read `.github/copilot-progress.md`
2. Check proposal.md for current status
3. Check tasks.md for progress markers
4. Resume from `in-progress` marker

**Session End:**
1. Update tasks.md with current phase status
2. Update proposal.md with current percentage
3. Create/update STATUS.md if complex
4. Write session summary to `.github/copilot-progress.md`

---

## Automation Examples

### Example 1: Starting Feature 1.3.1

**Files to Create/Update:**
1. proposal.md: `Status: 🟡 IN PROGRESS - 0% COMPLETE`
2. tasks.md: All tasks listed, first marked `[-]`
3. spec.md: Already exists with requirements

**Result:**
- Feature tracked
- Progress visible
- Next steps clear

### Example 2: Phase 1 Complete (1.3.1)

**Files to Update:**
1. proposal.md: Status → `🟡 IN PROGRESS - 17% COMPLETE`
2. tasks.md: 
   - Phase 1 tasks → `[x]` with timestamps
   - Phase 2 tasks → `[-]` ready marker
   - Summary: `✅ COMPLETE (1 of 6) | 🟡 READY (1 of 6)`

**Result:**
- 17% progress visible
- Phase 2 can start
- Continuity preserved

### Example 3: Feature Complete

**Files to Update:**
1. proposal.md: Status → `✅ APPROVED` or `✅ COMPLETE`
2. tasks.md: All → `[x]`, Summary → `✅ COMPLETE (6 of 6)`
3. STATUS.md: Final report with all results

**Result:**
- Feature marked done
- All work documented
- Ready for next feature

---

## 📋 Progress Tracking & Session Management

### Development Session Workflow

For features in `openspec/changes/`, maintain progress through OpenSpec files:

1. **Initialize Progress**: Check `proposal.md` for current status
2. **Progress Documentation**: Update `proposal.md` and `tasks.md` at each phase completion
3. **Feature Tracking**: Use `proposal.md` (status %), `tasks.md` (detailed tasks), and `STATUS.md` (for complex features)
4. **File Synchronization**: Keep proposal.md % in sync with tasks.md phase markers
5. **Work One Task at a Time**: Mark one task as `[-]` (in-progress) before starting work
6. **Milestone Updates**: Create/update `STATUS.md` at 25% and 50% milestones
7. **Update Progress**: Mark tasks as `[x]` immediately after finishing with timestamp
8. **User Checkpoints**: Include validation points between phases
9. **Session Summary**: Maintain status in `proposal.md` and `tasks.md`

### Progress States
- **`not-started` / `[ ]`**: Task not yet begun
- **`in-progress` / `[-]`**: Currently working on this task (limit to one at a time)
- **`completed` / `[x]`**: Task finished successfully with timestamp

---

## ⚠️ CRITICAL: AUTOMATIC PROGRESS UPDATE WORKFLOW

**EVERY TIME a task is completed, this workflow MUST be executed:**

### Step-by-Step Automatic Update Process

**When you complete a task and mark it `[x]`:**

1. **Open the change folder** (e.g., `openspec/changes/1.0-feature-name/`)

2. **Count total tasks in tasks.md**
   - Go through entire file and count all `[ ]`, `[-]`, and `[x]` boxes
   - Example: "47 total tasks"

3. **Count completed tasks**
   - Count only `[x]` boxes
   - Example: "32 tasks currently marked [x]"

4. **Calculate percentage**
   - Formula: (Completed ÷ Total) × 100
   - Example: (32 ÷ 47) × 100 = **68%**

5. **Update proposal.md IMMEDIATELY**
   - Find the `**Overall Progress:**` line
   - Replace with: `**Overall Progress:** 68% ✅`
   - Also update `**Status:**` line if approaching 100%

6. **Update tasks.md phase headers**
   - Look for phase sections like `### Docker Setup ✅ PHASE 1 COMPLETE`
   - If all tasks in a phase are `[x]`, ensure header shows ✅ COMPLETE
   - If still in progress, show 🟡 PHASE X IN PROGRESS

7. **At 100% completion**
   - Update `**Status:**` in proposal.md to: `✅ **COMPLETE - 100% COMPLETE**`
   - Update all phase headers to show ✅ COMPLETE
   - Update final line in tasks.md to: `**Status:** 100% Complete | Ready for archival`

### Implementation Rule (For AI Agents)

**BEFORE completing this task, automatically:**

```
DO NOT mark this as final until you have:
✓ Updated tasks.md with [x] and timestamp
✓ Recalculated: (completed_count ÷ total_count) × 100
✓ Updated proposal.md **Overall Progress:** line
✓ Updated all affected phase headers
✓ Verified no tasks left in current phase
✓ Ran 'openspec validate' to confirm structure
```

### Task Completion Format

Mark task with completion timestamp:
```markdown
- [x] Task description - **DONE [14:45]**
- [-] Current task - **Phase X: In Progress**
- [ ] Next task - **Phase X: Ready**
```

### Progress Percentage Update

```markdown
**Status:** 🟡 **IN PROGRESS - 68% COMPLETE**
**Overall Progress:** 68% ✅  
```

**When 100% is reached:**
```markdown
**Status:** ✅ **COMPLETE - 100% COMPLETE**
**Overall Progress:** 100% ✅  
```

### Phase Headers Update

```markdown
### Docker Setup ✅ PHASE 1 COMPLETE
- [x] Task 1 - **DONE [14:30]**
- [x] Task 2 - **DONE [14:35]**
```

### Automation Checklist (After Each Task)
- [ ] Mark task as `[x]` with timestamp
- [ ] Recalculate overall % completion
- [ ] Update `**Overall Progress:** X%` in proposal.md
- [ ] Update phase headers if all tasks in phase are done
- [ ] If 100%, update status to `✅ COMPLETE - 100%`
- [ ] If reaching 25%, 50%, 75%, update phase summary

---

## Creating Specs Correctly (Prevent > Fix)

### Before You Start: Prevention Checklist

**✅ ALWAYS do these 3 things BEFORE creating your spec deltas:**

1. **Check what specs already exist:**
   ```bash
   ls openspec/specs/
   # Lists all existing capability specs
   # If battery/ doesn't exist → you'll use ADDED for battery spec
   # If battery/ exists → you'll use MODIFIED/REMOVED for battery spec
   ```

2. **Understand the ADDED vs MODIFIED rule (hardcoded):**
   - ✅ **Use ADDED**: For specs that don't exist yet in `openspec/specs/`
   - ✅ **Use MODIFIED**: For specs that already exist in `openspec/specs/`
   - ✅ **Use REMOVED**: For removing requirements from existing specs
   - ❌ **NEVER use MODIFIED/REMOVED**: On new specs (doesn't exist yet)

3. **Ensure proposal.md has required sections:**
   - `## Why` - Business/technical justification
   - `## What Changes` - List of modifications
   - Proper delta headers in `specs/[capability]/spec.md`

---

### The Golden Rule - Get It Right the First Time

**ONE RULE PREVENTS ALL VALIDATION ERRORS:**

> When creating a spec delta in `openspec/changes/[change-id]/specs/[capability]/spec.md`:
> - **IF the spec doesn't exist in `openspec/specs/`** → use `## ADDED Requirements`
> - **IF the spec already exists in `openspec/specs/`** → use `## MODIFIED Requirements` or `## REMOVED Requirements`

**That's it.** Follow this one rule and validation will pass.

---

### Correct Pattern: First-Time Spec Creation

**Scenario: Creating the battery spec for the first time**

```bash
# Step 1: Check if spec exists
ls openspec/specs/battery/spec.md
# Result: "cannot find" → Spec doesn't exist yet

# Step 2: In your change, use ADDED
# File: openspec/changes/1.4-fix-infinite-loop/specs/battery/spec.md
```

```markdown
# Delta: Battery Specification

## ADDED Requirements

### Requirement: Infinite Loop Prevention
The system MUST prevent schedule regeneration cascades by implementing a 60-second cooldown between regenerations.

#### Scenario: Cascade prevention during high load
- **WHEN** multiple price change events trigger schedule regeneration within 60 seconds
- **THEN** subsequent regeneration requests are ignored
- **AND** cooldown timer is logged for monitoring

### Requirement: Price Context for AI
The AI strategy MUST receive price context including percentages vs minimum price.

#### Scenario: AI receives pricing context
- **WHEN** AI is invoked to determine charging schedule
- **THEN** price object includes: current_price, min_price, percentage_vs_min
- **AND** AI can reason about whether to charge or wait
```

✅ **This is correct.** No validation errors.

---

### Correct Pattern: Modifying Existing Spec

**Scenario: Battery spec already exists, modifying it**

```bash
# Step 1: Check if spec exists
ls openspec/specs/battery/spec.md
# Result: File exists → Spec already exists

# Step 2: In your change, use MODIFIED
# File: openspec/changes/2.1-improve-ai/specs/battery/spec.md
```

```markdown
# Delta: Battery Specification

## MODIFIED Requirements

### Requirement: Infinite Loop Prevention
The system MUST prevent schedule regeneration cascades by implementing a 60-second cooldown between regenerations.
**NEW:** Cooldown now applies per-source (price changes, manual triggers, solar forecast) for granular control.

#### Scenario: Per-source cooldown enforcement
- **WHEN** price change triggers regeneration
- **THEN** next price-triggered regeneration waits 60 seconds
- **AND** manual triggers can still force immediate regeneration if needed

### Requirement: Price Context for AI
The AI strategy MUST receive price context including percentages vs minimum price.
**UNCHANGED** - See original spec for details.
```

✅ **This is correct.** Uses MODIFIED because spec already exists.

---

### ❌ Common Mistake (Avoid This)

**Wrong: Using MODIFIED on new spec**

```markdown
# File: openspec/changes/1.4-fix-infinite-loop/specs/battery/spec.md

## MODIFIED Requirements  # ❌ WRONG! Spec doesn't exist yet!
### Requirement: Infinite Loop Prevention
The system MUST prevent schedule regeneration cascades...
```

**Error you'll get:**
```
battery: target spec does not exist; only ADDED requirements are allowed for new specs.
```

**Why this happens:**
- You used `## MODIFIED` but the spec doesn't exist in `openspec/specs/` yet
- Archive process tries to modify a spec that doesn't exist (impossible)
- Validation catches this and fails

**Prevention:**
- Check if spec exists BEFORE choosing ADDED vs MODIFIED
- New changes = ADDED
- Follow-up changes = MODIFIED

---

### Proposal.md Template (Required Sections)

**Always include these sections in proposal.md to pass validation:**

```markdown
# Proposal: Infinite Loop Prevention Fix

**Version:** 1.4  
**Status:** 🟡 **IN PROGRESS - 0% COMPLETE**

## Executive Summary

Brief 1-2 sentence overview of what's changing.

## Why

Explain the business or technical problem being solved:
- Battery AI strategy was stuck in regeneration loops
- Each price update triggered immediate recalculation
- Cascade exhausted all resources in seconds
- Result: System became unresponsive

## What Changes

List all modifications:
- Added 60-second cooldown timer to prevent cascade
- Implemented price context object for AI (percentages)
- Removed min_profit_threshold constraint
- Added graceful fallback for empty price data

## Benefits

What improves:
- Battery AI now charges at better prices (37% savings)
- System stability during high price volatility
- Clearer AI decision reasoning

## Risk Assessment

What could go wrong:
- Cooldown might delay necessary emergency charges (mitigated by manual override)
- AI behavior changes based on new price context (covered by integration tests)

---

## Progress Tracking

**Status:** 🟡 **IN PROGRESS - 0% COMPLETE**  
**Completed Tasks:** 0 of 15  
**Last Updated:** [date]
```

---

### Spec Delta Template (Required Format)

**Always use these headers in `specs/[capability]/spec.md`:**

```markdown
# Delta: [Capability] Specification

## ADDED Requirements

### Requirement: [Name]
The system **SHALL/MUST** [behavior statement].

#### Scenario: [Name]
- **WHEN** [trigger]
- **THEN** [expected result]

## MODIFIED Requirements

### Requirement: [Name]
The system **SHALL/MUST** [behavior statement].

#### Scenario: [Name]
- **WHEN** [trigger]
- **THEN** [expected result]

## REMOVED Requirements

### Requirement: [Name]
Removing [old behavior] because [reason].
```

---

### Validation Checklist (Before Archiving)

Run this BEFORE archiving to catch issues early:

```bash
# 1. Validate structure
openspec validate [change-id] --strict

# 2. Manual checks
```

- [ ] proposal.md has `## Why` section
- [ ] proposal.md has `## What Changes` section
- [ ] specs/[capability]/spec.md uses only ADDED/MODIFIED/REMOVED (not both)
- [ ] Each requirement has at least one `#### Scenario:`
- [ ] Checked `ls openspec/specs/` to know which ADDED/MODIFIED to use
- [ ] Ran `openspec validate --strict` and got ✓ pass
- [ ] tasks.md all marked `[x]` complete
- [ ] README updated if public behavior changed

If all checks pass → Ready to archive!

---

### No Guessing: Decision Tree

```
START: Creating spec delta
  ↓
Does the spec already exist in openspec/specs/[capability]/spec.md?
  ↓
  ├─→ YES: Use ## MODIFIED Requirements
  │         (spec exists, we're changing it)
  │
  └─→ NO:  Use ## ADDED Requirements
           (spec doesn't exist, we're creating it)

Did you check correctly?
  ↓
  ├─→ YES: Proceed to create deltas
  │        All validation will pass
  │
  └─→ NO:  STOP and check again
           ls openspec/specs/[capability]/
```

**Example Complete proposal.md Structure:**
```markdown
# [Change Name] Proposal

## Why
[Business/technical justification - why this change is needed]

## What Changes
- Added: [new feature]
- Modified: [changed behavior]
- Removed: [deprecated feature]

## Impact
[Performance implications, compatibility, migration steps]

## Timeline
[Estimated completion, phases]

## Status
🟡 **IN PROGRESS - 0% COMPLETE**
```

---

## When to Deviate from This Pattern

**You may deviate if:**
- Feature is very simple (1-2 tasks): Skip STATUS.md
- Feature is in planning only: Keep proposal.md only
- Feature requires different structure: Document why in proposal.md

**You should NOT deviate:**
- When feature has multiple phases: Use full pattern
- When feature is complex: Always use full pattern
- When feature affects other teams: Always fully document

---

**Last Updated:** October 30, 2025  
**Status:** Active - Use for all OpenSpec features  
**Applies To:** All feature implementations in openspec/ folder
