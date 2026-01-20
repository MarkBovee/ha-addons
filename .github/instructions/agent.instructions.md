---
applyTo: '**'
---

# Coding Assistant Instructions (Spec-Driven)

The assistant has freedom to design and implement solutions, but must always work like a professional developer:
define expectations, plan steps, implement clean code, and verify results.

---

## 🚨 CRITICAL: READ THIS FIRST

**These rules are MANDATORY and must be followed before any other action:**

### 1. ⚠️ ALWAYS CREATE BRANCH FIRST (Phase 0)
**Before writing ANY code, ALWAYS work from a non-main branch:**
- ✅ If a related branch already exists for this change, continue using it (do NOT create a new branch).
- ✅ New feature/breaking change → `git checkout -b feature/[change-id]` + create OpenSpec change folder
- ✅ Bug fix → `git checkout -b fix/[descriptive-name]`
- ✅ Refactor → `git checkout -b refactor/[descriptive-name]`
- ✅ Documentation → `git checkout -b docs/[descriptive-name]`

**❌ NEVER work on main branch directly**
**❌ NEVER write code before moving to or creating the appropriate branch**

### 2. ⚠️ NO TEMPORARY REPORT FILES
**NEVER create these files:**
- ❌ `*_REPORT.md` (audit, compliance, status reports)
- ❌ `*_SUMMARY.md` (completion, project, cleanup summaries)
- ❌ `PROGRESS_*.md`, scattered `STATUS.md` files
- ❌ `*_COMPLETE.md`, `*_GUIDE.md` (unless in /docs/ as permanent content)

**Where information belongs:**
- Progress → `tasks.md` checkmarks: `[x]` done, `[-]` in progress
- Status at milestones → `STATUS.md` (complex OpenSpec features only, 25%+ milestones)
- Historical → git commit messages
- Specifications → `openspec/specs/`
- Public docs → `README.md`, `/docs/`

### 3. ⚠️ MANDATORY DOCUMENTATION UPDATES (Phase 3.5)
**After code is ready, BEFORE final commit:**
1. ✅ Read all instruction files (agent, documentation, openspec, coding)
2. ✅ Update progress in canonical files (proposal.md, tasks.md, STATUS.md if needed)
3. ✅ Update public documentation (README.md if behavior changed)
4. ✅ Update OpenSpec specs if requirements changed
5. ✅ Verify no temporary report files exist
6. ✅ Final commit with documentation updates

**Without Phase 3.5, work is incomplete.**

---

## Decision Tree: Which Workflow?

**Start here to determine your workflow:**

```
┌─────────────────────────────────────────┐
│  Does this require code changes or      │
│  capability modifications?              │
└─────────────┬───────────────────────────┘
              │
      ┌───────┴────────┐
      │                │
     YES              NO
      │                │
      │           Simple documentation
      │           fix/typo → Phase 1
      │
      ▼
┌─────────────────────────────────────────┐
│  Is it a new feature, breaking change,  │
│  or architecture modification?          │
└─────────────┬───────────────────────────┘
              │
      ┌───────┴────────┐
      │                │
     YES              NO
      │                │
  OPENSPEC         BUG FIX /
   CHANGE         REFACTOR
      │                │
      ▼                ▼
Phase 0.1:      Phase 0.2:
Create          Create
OpenSpec        branch only
change +        (fix/*, refactor/*,
branch          docs/*)
```

**Examples:**
- ✅ New battery trading algorithm → **OpenSpec change** (Phase 0.1)
- ✅ Breaking API change → **OpenSpec change** (Phase 0.1)
- ✅ Fix grace period bug → **Bug fix branch** (Phase 0.2: `fix/grace-period`)
- ✅ Refactor price calculation → **Refactor branch** (Phase 0.2: `refactor/price-calc`)
- ✅ Update README → **Docs branch** (Phase 0.2: `docs/readme-update`)

---

## Safety Guard

Before proceeding with any task, ensure that the specifications are clear and unambiguous. If there is any room for misinterpretation, ask the user for clarification to obtain the best possible specs.

---

## ⚠️ MANDATORY FINAL PHASE (Phase 3.5)

**Every implementation MUST include Phase 3.5: Documentation & Progress Finalization.**

This is NOT optional. After your code is ready:
1. ✅ Read all instruction files (agent.instructions.md, documentation.instructions.md, openspec.instructions.md, coding.instructions.md)
2. ✅ Update progress in canonical files (proposal.md, tasks.md, STATUS.md)
3. ✅ Update public documentation (README.md, design.md, specs)
4. ✅ Final commit with documentation updates
5. ✅ Verify no temporary report files exist

**Without Phase 3.5, work is incomplete.** See detailed checklist below under "PHASE 3.5: DOCUMENTATION & PROGRESS FINALIZATION".

---

## 🔹 Quick Reference (OpenSpec-Aligned Checklist)

### PHASE 0: INITIATION (Create OpenSpec Change or Branch)

**Does this task require code changes or capability modifications?**

- **YES (New Feature / Breaking Change)** → Go to Phase 0.1
- **NO (Bug fix / Docs only / Typo)** → Go to Phase 1

#### 0.1 Create OpenSpec Change (Feature/Breaking Changes)
- [ ] Run: `openspec spec list --long` (review existing capabilities)
- [ ] Choose unique `change-id`: kebab-case, verb-led (e.g., `add-solar-forecast`, `update-pricing-logic`)
- [ ] Choose change number: Next sequential number (see versioning rules below)
- [ ] Create folder: `openspec/changes/[number]-[change-id]/` (e.g., `1.2-add-solar-forecast/`)
- [ ] Create branch: `git checkout -b feature/[change-id]` (use change-id, not number)
- [ ] Scaffold files:
  - `proposal.md` (add **Version:** [number] at top, why, what, impact, timeline)
  - `tasks.md` (implementation checklist with phases)
  - `design.md` (optional: technical decisions if complex)
  - `specs/[capability]/spec.md` (delta requirements: ADDED/MODIFIED/REMOVED)
- [ ] Validate: `openspec validate [number]-[change-id] --strict`

**Change Numbering Rules:**
- **Sequential numbering:** Each new change gets the next number (1.0, 1.1, 1.2, 1.3, etc.)
- **Purpose:** Short reference ID instead of typing full change-id name
- **Check existing:** Run `ls openspec/changes/` to see highest number, use next
- **Examples:** 
  - First change: `1.0-disable-ai-enable-smart-trading`
  - Second change: `1.1-improve-instruction-compliance`
  - Third change: `1.2-stabilize-ai-battery-strategy`
- **Folder naming:** Always `[number]-[change-id]/` format (number prefix)
- **Version in proposal.md:** Must match folder number (e.g., **Version:** 1.2)

**Version Updates Within a Change:**
- **Minor refinements:** Keep same number, document in version history
- **Major scope changes:** Rare - only if complete redesign needed
- **Version history:** Track all updates in proposal.md version history section

#### 0.2 Create Git Branch (Bug Fixes / Refactors / Docs)
- [ ] Branch type: `fix/[descriptive-name]` or `refactor/[descriptive-name]` or `docs/[descriptive-name]`
- [ ] Example: `fix/trading-strategy-grace-period` or `docs/price-bucketing-algorithm`
- [ ] Run: `git checkout -b [branch-name]`

**⚠️ VALIDATION GATE: Phase 0 → Phase 1**
- [ ] Branch created and not on `main`
- [ ] For OpenSpec changes: Folder structure validated with `openspec validate --strict`
- [ ] For OpenSpec changes: Version number added to folder name and proposal.md
- [ ] Git status clean (no uncommitted scaffolding)

---

### PHASE 1: SPECIFICATION & PLANNING

1. **Define Spec** → What success looks like (measurable, testable outcomes)
   - For OpenSpec changes: Document in `proposal.md` (Executive Summary section)
   - For bug fixes: Document expected vs actual behavior
   - **Success criteria:** Can someone else understand what "done" means?

2. **Identify Risks & Dependencies** → Blockers, requirements, time estimates
   - For OpenSpec changes: Document in `proposal.md` (Risk Assessment section)
   - List: external APIs, tools, permissions, breaking changes
   - **Success criteria:** Could implementation start without unknown blockers?

3. **Create Plan** → Steps with validation points (checkpoint after each major step)
   - For OpenSpec changes: Break into phases in `tasks.md`
   - Example phases: 1) Config 2) Core Logic 3) Testing 4) Documentation
   - **Success criteria:** Each step has a clear "done" definition

4. **Break into Tasks** → Concrete, testable coding tasks
   - For OpenSpec changes: Use `tasks.md` with checkboxes
   - Format: `- [ ] 1.1 Task description` (links to phase)
   - **Success criteria:** Each task takes 15-60 minutes and has measurable output

5. **Review Plan** ✅ → Does plan satisfy spec? Are all risks addressed?
   - [ ] Spec: Plan covers all requirements from step 1
   - [ ] Risks: All identified risks have mitigation strategies
   - [ ] Tests: Testing strategy defined (unit, integration, end-to-end)
   - [ ] Docs: Documentation updates planned
   - [ ] OpenSpec: Change properly scoped (not too large, not too small)
   - **If gaps found:** Revise plan (return to step 3)
   - **If satisfied:** Proceed to Phase 2

**⚠️ VALIDATION GATE: Phase 1 → Phase 2**
- [ ] Specification is clear and measurable
- [ ] All risks identified with mitigation strategies
- [ ] Plan broken into concrete, testable tasks
- [ ] User has approved the plan (for significant changes)
- [ ] **STOP if plan unclear:** Return to Phase 1 for clarification

---

### PHASE 2: IMPLEMENTATION & VERIFICATION

**⚠️ WARNING: Did you create a branch in Phase 0? If not, STOP and create one now!**

6. **Implement** → Write full working code (no placeholders)
   - [ ] Code follows coding standards (see `coding.instructions.md`)
   - [ ] Apply DRY principle: check for existing similar code
   - [ ] Include error handling and logging
   - [ ] For OpenSpec changes: Update `tasks.md` progress as you go
     - Mark tasks `[x]` with timestamp: `- [x] Task - **DONE [HH:MM]**`
     - Update `proposal.md` progress percentage regularly
   - [ ] Build compiles: 0 errors, 0 warnings
   - [ ] All tests passing (existing + new)
   - **Success criteria:** Code is production-ready, not a draft

7. **Verify Results** ✅ → Do actual results match spec from Step 1?
   - [ ] **Functional:** All spec requirements met (from Step 1)
   - [ ] **Testing:** 
     - All existing tests pass
     - All new tests pass (unit, integration, end-to-end)
     - Code coverage ≥85% for new code paths
   - [ ] **Quality:**
     - Build clean (0 errors, 0 warnings)
     - No compiler warnings or hints
     - Code is self-documenting or well-commented
   - [ ] **For OpenSpec changes:**
     - Run `openspec validate [change-id] --strict` (confirms structure)
     - All tasks marked `[x]` in `tasks.md`
     - `proposal.md` shows 100% complete
     - `STATUS.md` updated with final results
   - **If issues found:** Debug and fix (return to step 6)
   - **If all pass:** Ready for Phase 3.5 (Documentation)

**⚠️ VALIDATION GATE: Phase 2 → Phase 3.5**
- [ ] All code compiles without errors or warnings
- [ ] All tests passing (100%)
- [ ] Code coverage ≥85% for new code
- [ ] For OpenSpec: `openspec validate --strict` passes
- [ ] **STOP if validation fails:** Fix issues before proceeding

---

### PHASE 3: COMPLETION (Commit & Archive)

**⚠️ WARNING: Before committing, have you completed Phase 3.5 (Documentation)? See below!**

8. **Commit Changes** → Clear message with what and why
   - Branch commit message format:
     ```
     [type]: [description]
     
     [Optional details about what changed and why]
     ```
   - Examples:
     - `feat: implement price bucketing service with percentile calculations`
     - `fix: add grace period to prevent charge cycling`
     - `docs: update README with Smart Trading algorithm`

9. **For OpenSpec Changes: Archive** (after testing & approval)
   - [ ] All phases complete and tested
   - [ ] Stakeholders approved changes
   - [ ] Run: `openspec archive [change-id] --yes`
   - [ ] This merges specs into `openspec/specs/` (canonical truth)
   - [ ] Change folder moved to `openspec/changes/archive/YYYY-MM-DD-[change-id]/`
   - [ ] Create PR with archived change and new specs

10. **Merge to Main** → Branch becomes canonical
    - [ ] All tests passing in CI/CD
    - [ ] Code review approved (if applicable)
    - [ ] For OpenSpec changes: Latest specs are in `openspec/specs/`
    - [ ] Delete branch: `git branch -d [branch-name]`  

---

### 🚨 PHASE 3.5: DOCUMENTATION & PROGRESS FINALIZATION (MANDATORY - DO NOT SKIP)

**⚠️ CRITICAL FINAL STEP**: This step is **ALWAYS required**, even for small changes. It happens AFTER code is ready but BEFORE final commit.

11. **Read All Instruction Files** → Ensure compliance with current standards
    - [ ] Read: `agent.instructions.md` (this file - workflow standards)
    - [ ] Read: `documentation.instructions.md` (docs standards, NO REPORT FILES)
    - [ ] Read: `openspec.instructions.md` (OpenSpec workflow and progress tracking)
    - [ ] Read: `coding.instructions.md` (code standards)
    - [ ] For OpenSpec changes: Read `openspec/AGENTS.md` (OpenSpec workflow)
    - **Purpose:** Catch any violations early, apply latest standards
    - **Success criteria:** Know what standards apply to your work

12. **Update Progress Documentation** → All progress tracked in canonical files
    - **For OpenSpec changes:**
      - [ ] `proposal.md`: Update `**Status:**` line to final percentage (should be 100%)
      - [ ] `proposal.md`: Update completion date (today's date)
      - [ ] `tasks.md`: All tasks marked `[x]` with timestamps
      - [ ] `tasks.md`: All phase headers show completion status
      - [ ] `STATUS.md`: Updated with final results summary (if complex feature)
      - [ ] Verify no temporary report files exist (*.REPORT.md, *_SUMMARY.md, etc.)
    - **For bug fixes/refactors:**
      - [ ] Update commit message to clearly explain the fix/change
      - [ ] Include before/after comparison if helpful
      - [ ] Reference any related issues or requirements
    - **Success criteria:** Someone can understand what was done by reading canonical files

13. **Update Public Documentation** → Ensure README and specs reflect changes
    - **For code changes:**
      - [ ] `README.md`: Updated if public-facing behavior changed
      - [ ] `README.md`: Architecture section updated if structure changed
      - [ ] `README.md`: Configuration section updated if new settings added
    - **For OpenSpec changes:**
      - [ ] Delta spec (`openspec/changes/[id]/specs/*/spec.md`): Documents ADDED/MODIFIED/REMOVED requirements
      - [ ] Design doc (`openspec/changes/[id]/design.md`): Explains technical decisions (optional but recommended)
      - [ ] Verify: No temporary files in `openspec/changes/[id]/` (only approved: proposal.md, tasks.md, design.md, STATUS.md, specs/)
    - **Success criteria:** Future developers understand what changed and why

14. **Final Commit & Status Update** → Lock in all documentation
    - [ ] `git add` all documentation changes (proposal.md, tasks.md, STATUS.md, README.md, etc.)
    - [ ] `git commit` with clear message: "docs: [update type] - [brief description]"
    - [ ] Example: `"docs: Update proposal & tasks - disable-ai-enable-smart-trading 100% COMPLETE"`
    - [ ] Verify: `git status` shows clean working directory
    - [ ] Verify: All docs reflect current state (no stale information)
    - **Success criteria:** Git history shows exactly what was implemented

---

**🔴 RED FLAGS (Stop & Fix Before Proceeding)**

- ❌ Temporary report files found: `PROGRESS_*.md`, `*_SUMMARY.md`, `*_COMPLETE.md`
- ❌ `proposal.md` still shows incomplete percentage (should be 100% or archived)
- ❌ `tasks.md` has unchecked tasks (should all be `[x]` or properly documented as skipped)
- ❌ `README.md` or specs don't reflect the changes you made
- ❌ Instruction files show standards you didn't apply
- ❌ Temporary files in `openspec/changes/[id]/` (violates OpenSpec standards)

If any red flags found: **Go back to Phase 2 and fix before committing**

**⚠️ VALIDATION GATE: Phase 3.5 → Final Commit**
- [ ] All instruction files read and standards applied
- [ ] Progress updated in canonical files (proposal.md, tasks.md)
- [ ] Public documentation updated (README.md if behavior changed)
- [ ] OpenSpec specs updated if requirements changed
- [ ] NO temporary report files exist anywhere
- [ ] **STOP if any red flags:** Fix before final commit

---

## Detailed Workflow (Phase by Phase)

### Phase 0: Initiation & Branch Setup

#### 0.1 For OpenSpec Changes (New Features, Breaking Changes, Architecture Changes)

**When to create OpenSpec change:**
- Adding new capability or feature
- Making breaking changes to existing APIs
- Changing core architecture or patterns
- Significant performance optimizations
- Security or compliance changes

**Setup steps:**
1. Review existing capabilities: `openspec spec list --long`
2. Choose unique verb-led change ID: `add-solar-forecast`, `update-pricing-logic`, `disable-ai-enable-smart-trading`
3. Create folder structure:
   ```
   openspec/changes/[change-id]/
   ├── proposal.md          # Why, what, impact, timeline
   ├── tasks.md             # Implementation phases with checkboxes
   ├── design.md            # (Optional) Technical architecture decisions
   └── specs/               # Delta specifications
       └── [capability]/
           └── spec.md      # ADDED/MODIFIED/REMOVED requirements
   ```
4. Create git branch (same name as change-id):
   ```bash
   git checkout -b feature/[change-id]
   ```
5. Validate structure: `openspec validate [change-id] --strict`

#### 0.2 For Bug Fixes, Refactors, or Documentation

**Branch naming convention:**
- Bug fix: `fix/[descriptive-name]` (e.g., `fix/grace-period-calculation`)
- Refactor: `refactor/[descriptive-name]` (e.g., `refactor/extract-price-logic`)
- Documentation: `docs/[descriptive-name]` (e.g., `docs/trading-strategy-guide`)

**Setup steps:**
1. Create branch: `git checkout -b [branch-type]/[name]`
2. No OpenSpec change needed (unless it's substantial)
3. Proceed directly to Phase 1 (Spec & Planning)

---

### Phase 1: Specification & Planning (Pre-Implementation)

**Timeline: 15-30 minutes** | **Deliverable: Plan document + task checklist**

#### Step 1.1: Define Specification
What does success look like? Document in measurable, testable terms.

**For OpenSpec changes:** Fill `proposal.md` sections:
- Executive Summary: What are we changing and why?
- What's Changing: Table with before/after comparison
- Benefits: Quantified improvements (cost, performance, etc.)
- Success Criteria: Specific pass/fail criteria

**For bug fixes:** Document:
- Current behavior (broken)
- Expected behavior (correct)
- How to verify the fix works

**Validation:** Could someone else understand "done" without asking?

#### Step 1.2: Identify Risks & Dependencies
What could block implementation? What's required?

**For OpenSpec changes:** Fill `proposal.md` Risk Assessment:
- External dependencies (APIs, tools, libraries)
- Breaking changes and migration paths
- Data migration or backward compatibility needs
- Time estimates per phase

**Questions to answer:**
- What APIs or services are needed?
- Are there permission/access requirements?
- Could this break existing integrations?
- What's the rollback strategy?

#### Step 1.3: Create Implementation Plan
Break the work into logical phases with validation points.

**For OpenSpec changes:** Create `tasks.md` with phases:
```markdown
## Phase 1: Configuration & Setup
- [ ] 1.1 Update configuration files
- [ ] 1.2 Register DI services
- [ ] 1.3 Verify build succeeds

## Phase 2: Core Logic
- [ ] 2.1 Implement main algorithm
- [ ] 2.2 Add helper methods
- [ ] 2.3 Write unit tests

## Phase 3: Integration
- [ ] 3.1 Integrate with existing services
- [ ] 3.2 Write integration tests

## Phase 4: Documentation
- [ ] 4.1 Update README
- [ ] 4.2 Add code comments
- [ ] 4.3 Final testing
```

**Validation:** Each phase has a clear checkpoint and measurable deliverable.

#### Step 1.4: Break into Concrete Tasks
What are the specific coding tasks for this sprint?

**Format (for tasks.md):**
```markdown
- [ ] 1.1 Update appsettings.json with new config section
- [ ] 1.2 Create DependencyInjection helper class
- [ ] 1.3 Register services in Program.cs
- [ ] 1.4 Verify build compiles without errors
```

**Validation:** Each task takes 15-60 minutes and produces a measurable artifact.

#### Step 1.5: Validate Plan Against Spec ✅
Before coding, ensure the plan will achieve the spec.

**Checklist:**
- [ ] Spec: Does plan address all requirements from Step 1.1?
- [ ] Risks: Does plan mitigate all identified risks?
- [ ] Tests: Is testing strategy defined (unit, integration, E2E)?
- [ ] Docs: Are documentation updates planned?
- [ ] OpenSpec: Is change properly scoped (not too large)?
- [ ] Timeline: Are time estimates reasonable?
- [ ] Git: Is branch properly created and ready?

**If issues found:** Revise plan → Return to Step 1.3  
**If all clear:** Proceed to Phase 2

---

### Phase 2: Implementation & Verification (During & After Coding)

**Timeline: Varies** | **Deliverable: Working code + passing tests**

#### Step 2.1: Implement Code
Write production-ready code following professional standards.

**Standards:**
- Apply **DRY principle**: Check for existing similar code before writing new
- Include **error handling**: Try-catch, validation, logging
- Follow **coding conventions**: See `coding.instructions.md`
- **No placeholders**: Code must be complete and functional

**For OpenSpec changes: Track progress in real-time**
```markdown
- [x] 1.1 Update appsettings.json - **DONE [14:30]**
- [-] 1.2 Create DependencyInjection helper - **In Progress [15:00]**
- [ ] 1.3 Register services - **Ready**
```

**Update files as you work:**
- Mark tasks in `tasks.md` with `[x]` and timestamp
- Update `proposal.md` progress percentage: `(Completed Tasks ÷ Total Tasks) × 100`
- Run builds frequently: `dotnet build`
- Run tests frequently: `dotnet test`

**Success criteria:**
- Build: 0 errors, 0 warnings
- All existing tests: PASSING
- Code is clean and maintainable

#### Step 2.2: Write Comprehensive Tests
Verify functionality at unit, integration, and acceptance levels.

**For new code:**
- Write unit tests for isolated components
- Write integration tests for component interactions
- Write acceptance tests for end-to-end workflows

**For OpenSpec changes:** Create tests in `Tests/` folder
- Example: `Tests/PriceBucketingServiceTests.cs` (unit)
- Example: `Tests/TradingStrategyIntegrationTests.cs` (integration)

**Success criteria:**
- All tests passing: 100%
- Code coverage: ≥85% for new code paths
- No flaky tests (all pass consistently)

#### Step 2.3: Verify Results Against Spec ✅
Do actual results match the spec from Step 1.1?

**Functional verification (from Spec):**
- [ ] Requirement 1: Works as specified? ✅ or ❌
- [ ] Requirement 2: Works as specified? ✅ or ❌
- [ ] Edge cases: Handled correctly? ✅ or ❌

**Testing verification:**
- [ ] All existing tests: PASSING
- [ ] All new tests: PASSING (>85% coverage)
- [ ] Build: 0 errors, 0 warnings
- [ ] No compiler hints or warnings

**For OpenSpec changes: Validate structure**
- [ ] Run: `openspec validate [change-id] --strict`
- [ ] All tasks marked `[x]` in `tasks.md`
- [ ] `proposal.md` shows 100% complete
- [ ] `STATUS.md` updated with final summary
- [ ] Specs properly formatted with ADDED/MODIFIED/REMOVED

**If issues found:** 
- Debug the issue
- Consult Spec from Step 1.1 (what should it do?)
- Fix code → Return to Step 2.1
- Re-run tests → Verify again

**If all pass:** Proceed to Phase 3

---

### Phase 3: Completion (Commit, Archive, Merge)

**Timeline: 10-15 minutes** | **Deliverable: Merged code on main**

#### Step 3.1: Commit Changes
Save your work with clear, descriptive commit message.

**Commit message format:**
```
[type]: [description]

[Optional: detailed explanation of what changed and why]
```

**Types:**
- `feat:` - New feature or capability
- `fix:` - Bug fix
- `refactor:` - Code restructuring
- `docs:` - Documentation update
- `test:` - Test additions or fixes

**Examples:**
```
feat: implement price bucketing service with percentile calculations

- CalculatePercentiles() method with linear interpolation
- SOC-to-threshold mapping (P20/P40/P60)
- 7 unit tests, all passing
- Integrated into TradingStrategy via DI

docs: update README with Smart Trading algorithm documentation

- Added pricing strategy explanation
- Added configuration examples
- Added SOC threshold table

fix: add grace period to prevent rapid charge triggering

- 15-minute minimum between charge triggers
- Integrated into MonitorAndAdjustActivePeriod()
- All tests passing (16/16)
```

#### Step 3.2: For OpenSpec Changes - Archive
After implementation is complete and tested, archive the change.

**Prerequisites:**
- [ ] All phases implemented and tested
- [ ] All tests passing (100%)
- [ ] Build clean (0 errors, 0 warnings)
- [ ] Stakeholders approved (if required)

**Archive steps:**
```bash
# Validate structure is correct
openspec validate [change-id] --strict

# Archive the change (merges into canonical specs)
openspec archive [change-id] --yes

# This will:
# 1. Move specs from openspec/changes/[id]/specs/ → openspec/specs/
# 2. Move change folder → openspec/changes/archive/YYYY-MM-DD-[change-id]/
# 3. Mark change as complete in archive
```

**Result:** `openspec/specs/` now contains the latest canonical specifications

#### Step 3.3: Create Pull Request
Submit work for review before merging to main.

**PR checklist:**
- [ ] Branch created from `main`
- [ ] All commits are clean and well-documented
- [ ] For OpenSpec changes: Include archived change and new specs
- [ ] All tests passing in CI/CD
- [ ] No merge conflicts with main
- [ ] Code review approved (if applicable)

#### Step 3.4: Merge to Main
After approval, merge branch and delete.

**Steps:**
```bash
# Update main with latest
git checkout main
git pull origin main

# Merge branch (use squash or merge commit as appropriate)
git merge feature/[change-id]

# Delete branch
git branch -d feature/[change-id]

# Push to remote
git push origin main
git push origin --delete feature/[change-id]
```

**Verification:**
- All GitHub CI/CD checks passed
- Branch fully merged and cleaned up
- For OpenSpec changes: Latest specs are in `openspec/specs/`

---

## Output Format (Present Work in This Order)

### For OpenSpec Changes:
1. **Change ID & Version** (e.g., `disable-ai-enable-smart-trading | Version 1.0`)
2. **Branch Created** (e.g., `feature/disable-ai-enable-smart-trading`)
3. **Specification Summary** (from `proposal.md`)
4. **Risks & Dependencies** (from `proposal.md`)
5. **Implementation Plan** (from `tasks.md` with phases)
6. **Code Changes** (Full files or patches with language tags)
7. **Test Results** (Unit + Integration tests passing count)
8. **Build Verification** (0 errors, 0 warnings)
9. **Documentation Updates** (README.md, inline comments, design.md)
10. **Completion Status** (proposal.md % complete, tasks.md checkboxes)

### For Bug Fixes / Refactors:
1. **Branch Created** (e.g., `fix/grace-period-calculation`)
2. **Expected vs Actual Behavior** (what's broken vs what should work)
3. **Root Cause Analysis** (why it's broken)
4. **Implementation Plan** (what changes will fix it)
5. **Code Changes** (Full files or patches)
6. **Test Results** (Verify fix works, no regressions)
7. **Verification** (Confirm spec from step 2 is met)

**Code formatting:**
- Use fenced code blocks with correct language tags (csharp, json, markdown, etc.)
- For multiple files: Provide each file in full
- Include line numbers for significant sections
- For patches: Show 3-5 lines of context before/after changes

**Progress tracking:**
- For OpenSpec changes: Use `proposal.md` and `tasks.md` for real-time progress
- For bug fixes: Document progress in commit messages and PR description
- Never commit temporary progress files (violates documentation standards)

---

## Coding Standards

**📋 Refer to `coding.instructions.md` for comprehensive coding standards and best practices.**

Key reminders during implementation:
- Apply **DRY principle** - check for existing similar code before adding new functionality
- **Post-implementation review** - after each code change, review for optimization opportunities  
- **Constructor optimization** - when adding properties that require changes in many places, consider making them optional with defaults or using builder patterns

---

## OpenSpec Progress Tracking

**📋 Refer to `openspec.instructions.md` for automated OpenSpec feature tracking.**

When implementing OpenSpec features:
- Update `proposal.md` status at phase boundaries (0%, 17%, 33%, 50%, etc.)
- Update `tasks.md` with progress markers as phases complete
- Create `STATUS.md` for complex/multi-phase features at 25% and 50% milestones
- Keep all files synchronized (proposal status ↔ tasks progress)
- Use consistent markers: ✅ (complete), 🟡 (ready/in-progress), ⏳ (pending)

**Key files to maintain:**
1. `proposal.md` - Executive status and percentage
2. `tasks.md` - Detailed task tracking with phase markers
3. `spec.md` - Requirements (locked once approved)
4. `STATUS.md` - Comprehensive reports (for complex features)

---

## Clarifications
- If expectations or validations are ambiguous → ask.  
- Do not guess hidden requirements.  
- Keep it light: do not add extras unless explicitly requested.
