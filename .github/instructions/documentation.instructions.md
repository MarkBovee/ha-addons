---
applyTo: '**'
---

# Documentation Standards for AI Agents (OpenSpec-Aligned)

This file contains rules and guidelines for creating and maintaining documentation in this repository. AI agents must follow these standards when creating, updating, or organizing documentation.

**This project uses OpenSpec (https://openspec.dev) for spec-driven development. Documentation follows a three-tier system: project docs (root README), canonical specs (openspec/specs/), and proposals (openspec/changes/).**

**For implementation workflow (Phase 0-3), see `agent.instructions.md`. This file focuses only on documentation file standards and organization.**

---

## 📋 Core Principles

1. **Single Source of Truth** - One comprehensive README per project/module + canonical specs in `openspec/specs/`
2. **OpenSpec Separation** - Proposed changes live in `openspec/changes/` with minimal structure
3. **Spec Deltas** - Requirements changes use `## ADDED|MODIFIED|REMOVED` format in spec deltas
4. **Clear Hierarchy** - Documentation organized by audience: project overview (README), specifications (openspec/), deep-dives (/docs/)
5. **Always Up-to-Date** - Update documentation with every related code change, archive changes after deployment
6. **Actionable Content** - Documentation should help users accomplish tasks
7. **NO REPORT FILES** - ⚠️ **CRITICAL**: Do NOT create temporary report, summary, or status files. Information belongs in actual documentation (README.md, proposal.md, tasks.md, etc.) or version control messages

---

## ⚠️ CRITICAL: NO TEMPORARY REPORT FILES

**NEVER create these files:**
- ❌ `*_REPORT.md` - Audit reports, compliance reports, status reports, deployment readiness reports
- ❌ `*_SUMMARY.md` - Completion summaries, project summaries, cleanup summaries, phase summaries
- ❌ `PROGRESS_*.md`, scattered `STATUS.md` files in multiple locations
- ❌ `*_COMPLETE.md`, `*_FINISHED.md` - Completion notifications
- ❌ `*_GUIDE.md` - Implementation guides, local testing guides, setup guides (unless in `/docs/` as permanent, reusable content)
- ❌ `PHASE_*.md` - Phase 1 results, Phase 2 results, etc.
- ❌ Any file that documents "what was done", "what changed", or "current status"

**Real examples of violations (DO NOT CREATE):**
```
❌ COMPLETION_SUMMARY.md
❌ IMPLEMENTATION_PLAN.md (use proposal.md instead)
❌ LOCAL_TESTING_GUIDE.md (unless permanent docs)
❌ PHASE_1_RESULTS.md, PHASE_2_RESULTS.md
❌ DEPLOYMENT_READINESS_REPORT.md
❌ OPENSPEC_UPDATE.md
❌ PROGRESS_TRACKER.md
```

**Where information belongs:**
| Type of Info | Goes To | Example |
|--------------|---------|---------|
| What project does | `README.md` | Architecture, features, setup |
| What changed in specs | `openspec/specs/[capability]/spec.md` | Current requirements |
| Why we're changing something | `openspec/changes/[id]/proposal.md` | Executive summary, rationale |
| What work needs to be done | `openspec/changes/[id]/tasks.md` | Task checklist with phases |
| Progress on tasks | Checkmarks in `tasks.md` | `- [x]` done, `- [-]` in progress |
| Status at milestones (25%+) | `openspec/changes/[id]/STATUS.md` | Complex features only |
| Implementation details | `openspec/changes/[id]/design.md` | Technical decisions |
| Historical information | Git commit messages | What was done and why |
| Public documentation | `README.md`, `/docs/` | User-facing guides |

**Why this matters:**
- ❌ Report files create clutter and confusion
- ❌ They become outdated quickly
- ❌ OpenSpec archival process expects minimal folder structure only
- ❌ Violates "single source of truth" principle
- ✅ Git history and commit messages are the proper audit trail
- ✅ Actual documentation (README.md, specs, proposals) is canonical

**Consequences of violations:**
- Change folders become bloated and hard to navigate
- Archival process fails or requires manual cleanup
- Duplication between temp files and canonical docs
- Confusion about which file has the "real" information

**⚠️ VALIDATION STEP: Before Committing**

Before committing ANY changes to OpenSpec change folders, run this check:

```powershell
# Check for prohibited files in OpenSpec change folder
ls openspec/changes/[change-id]/ -Recurse -File | Where-Object { 
    $_.Name -match '_REPORT\.md$|_SUMMARY\.md$|_COMPLETE\.md$|_GUIDE\.md$|PROGRESS.*\.md$|PHASE_.*\.md$'
}
```

**If ANY files are found:**
- ❌ STOP - Do not commit
- Delete prohibited files
- Move information to correct location (see table above)
- Re-validate before committing

**Allowed files in OpenSpec change folders:**
- ✅ `proposal.md` (REQUIRED)
- ✅ `tasks.md` (REQUIRED)
- ✅ `design.md` (OPTIONAL - complex features only)
- ✅ `STATUS.md` (OPTIONAL - 25%+ milestones, complex features only)
- ✅ `specs/[capability]/spec.md` (REQUIRED)

---

## 🗂️ Documentation Structure (Three Tiers)

### Tier 1: Project Documentation (Root Level `/`)
- **`README.md`** - Main project documentation (REQUIRED)
  - Project overview and purpose only
  - Quick start guide
  - High-level architecture overview
  - Folder structure with navigation
  - Links to detailed documentation and OpenSpec specs
  - **DO NOT include**: Detailed specs, implementation details, per-feature guides

### Tier 2: OpenSpec Specifications (`openspec/`)
**Source of Truth for all capabilities and features**

#### `openspec/specs/` (Current Truth)
- **Contains**: Canonical specifications for each capability
- **Structure**: One subfolder per capability (e.g., `openspec/specs/auth/`, `openspec/specs/api/`)
- **Files per capability**:
  - `spec.md` - Current requirements and scenarios (SHALL/MUST language)
  - `design.md` - Optional: Technical patterns and architecture decisions
- **Locked except during**: Change archival process
- **Updated by**: Archiving completed changes (not by direct editing)

#### `openspec/changes/` (Proposals)
- **Contains**: Proposed capability changes in isolated folders
- **Change Folder Structure** (must be minimal):
  ```
  openspec/changes/[change-id]/
  ├── proposal.md          # Why, what, impact (REQUIRED)
  ├── tasks.md             # Implementation checklist (REQUIRED)
  ├── design.md            # Technical decisions (OPTIONAL - only if complex)
  └── specs/               # Delta changes (REQUIRED)
      └── [capability]/
          └── spec.md      # ADDED/MODIFIED/REMOVED requirements
  ```
- **No other files** allowed in change folders (see "Anti-Patterns" section)
- **Archival**: After implementation, run `openspec archive [change-id] --yes` to merge specs back into `openspec/specs/`
- **Archived location**: `openspec/changes/archive/YYYY-MM-DD-[change-id]/`

### Tier 3: Documentation Folder (`/docs/`)
**Deep-dives that are NOT captured in OpenSpec specs**

Use **ONLY** for:
- Significant deep-dive architecture guides (>100 lines, not in `openspec/specs/`)
- Complex integration or operational runbooks
- Historical change documentation (after archival)
- Troubleshooting guides not part of spec scenarios

✅ **Appropriate for /docs/:**
- Detailed architecture diagrams with explanations (high-level version in README, detailed version here)
- Integration guides (e.g., complex Azure setup after deployment)
- Operational/disaster recovery runbooks
- FAQ/Troubleshooting for operational issues

❌ **NOT appropriate for /docs/:**
- General project information (belongs in README)
- Feature specifications (belongs in `openspec/specs/`)
- Implementation guides for features (belongs in proposal.md/tasks.md)
- Progress tracking or temporary documents
- Files that duplicate `openspec/specs/` content

### Module/Project Folders
Each major project folder (e.g., `terragrunt/poc/`, `app/`) **MAY** have its own README if:
- It's a standalone module that can be used independently
- It has specific usage instructions not covered by root README
- It needs to document module-specific configuration

---

## 📝 Documentation File Standards

### README.md Requirements

Every README.md must include (in order):

```markdown
# [Project Name]

[Brief 1-2 sentence description]

## Overview
- What this project does
- Why it exists
- Key features/capabilities

## Quick Start
- Prerequisites
- Installation steps
- Basic usage example

## Architecture
- High-level architecture diagram or description
- Key components and their relationships
- Technology stack

## Folder Structure
- Clear tree structure showing main folders
- Brief description of each folder's purpose

## Configuration
- Required configuration files
- Environment variables
- Example configurations

## Deployment
- Step-by-step deployment instructions
- Environment-specific considerations
- Validation steps

## Development
- How to contribute
- Development workflow
- Testing guidelines

## Documentation
- Links to detailed documentation in /docs/
- Link to OpenSpec specifications in openspec/specs/
- Related resources
- External references

## Support
- How to get help
- Issue reporting
- Contact information
```

### OpenSpec Change Folder Structure (STRICT)

Change folders in `openspec/changes/` MUST contain ONLY:

```
openspec/changes/[change-id]/
├── proposal.md       # REQUIRED - Why, what, and impact
├── tasks.md          # REQUIRED - Implementation checklist
├── design.md         # OPTIONAL - Only for complex technical decisions
├── STATUS.md         # OPTIONAL - Only at 25% and 50% milestones for complex features
└── specs/            # REQUIRED - Delta specifications
    └── [capability]/
        └── spec.md   # Changes using ADDED/MODIFIED/REMOVED format
```

**🚫 Prohibited files in change folders:**
- Progress tracking files (e.g., `PROGRESS.md`, `COMPLETION_SUMMARY.md`)
- Implementation guides (e.g., `IMPLEMENTATION_PLAN.md`, `LOCAL_TESTING_GUIDE.md`)
- Phase reports (e.g., `PHASE_*.md`, `DEPLOYMENT_READINESS_REPORT.md`)
- Temporary notes or scratch documents
- Multiple status files (only one `STATUS.md` allowed, and only for complex features)

**Rationale:** OpenSpec's minimal structure keeps proposals focused and auditable. Extra files create confusion and bloat during archival.

### 7️⃣ Creating OpenSpec Specifications

Specifications are the **source of truth** for your project's capabilities. They document what the system SHALL do, not how it's built.

#### When to Create a Spec

Create a new spec capability when:
- ✅ Adding a new feature or capability to the project
- ✅ Defining requirements for a major component (e.g., API, infrastructure pattern)
- ✅ Documenting existing features that should be formally specified
- ✅ Starting a new feature (create before or alongside the proposal)

#### Spec Folder Structure

Specs live in `openspec/specs/` organized by capability:

```
openspec/specs/
├── [capability-name]/
│   ├── spec.md          # REQUIRED - Requirements and scenarios
│   └── design.md        # OPTIONAL - Technical patterns and decisions
├── api/
│   ├── spec.md          # API requirements and endpoints
│   └── design.md        # API design patterns
├── infrastructure/
│   └── spec.md          # Infrastructure capabilities and patterns
└── database/
    └── spec.md          # Database schema and queries
```

#### Spec.md Format

Every `spec.md` should follow this structure:

```markdown
# [Capability] Specification

## Purpose
[1-2 sentences: what this capability does, why it exists]

## Requirements

### Requirement: [Name]
The system **SHALL** [describe mandatory behavior].

#### Scenario: [Name]
- **WHEN** [user/system action]
- **THEN** [expected result]
- **AND** [additional validations if needed]

### Requirement: [Another Feature]
The system **MUST** [describe critical behavior].

#### Scenario: [Success case]
- **WHEN** user performs action X
- **THEN** system returns Y
- **AND** result is logged in audit trail

#### Scenario: [Edge case]
- **WHEN** invalid input provided
- **THEN** system returns error code 400
- **AND** error message explains the problem

## Acceptance Criteria
- [ ] All requirements implemented and tested
- [ ] All scenarios pass manual/automated tests
- [ ] No breaking changes to existing APIs
- [ ] Documentation updated
```

#### Key Rules for Specs

1. **Use SHALL/MUST Language**
   - ✅ "The system SHALL authenticate users via managed identity"
   - ❌ "System should probably authenticate users"

2. **Include at Least One Scenario per Requirement**
   - Scenarios explain HOW the requirement is tested
   - Use WHEN/THEN format
   - Include edge cases and error conditions

3. **Make Specs Testable**
   - Requirements should be verifiable
   - Acceptance criteria should be measurable
   - Scenarios should have clear pass/fail criteria

4. **Separate Specs and Implementation**
   - Specs define WHAT (requirements)
   - Design.md defines HOW (technical approach)
   - Code implements the design

#### Example: Complete Spec

```markdown
# Quote API Specification

## Purpose
Provides REST endpoints for quote management, allowing clients to retrieve, create, and manage quotes. Serves as the primary integration point between frontend and backend services.

## Requirements

### Requirement: Quote Retrieval
The system SHALL return a quote by ID from Azure SQL Database via managed identity authentication.

#### Scenario: Valid quote ID provided
- **WHEN** client calls GET /quotes/{id}
- **THEN** system returns 200 with quote details
- **AND** response includes id, title, amount, createdAt

#### Scenario: Non-existent quote ID
- **WHEN** client calls GET /quotes/invalid-id
- **THEN** system returns 404 NotFound
- **AND** error message explains quote not found

### Requirement: Quote Creation
The system MUST create new quotes and store them in SQL with audit trail.

#### Scenario: Valid quote data
- **WHEN** client POSTs to /quotes with valid payload
- **THEN** system returns 201 Created
- **AND** response includes new quote ID
- **AND** quote is persisted to database

#### Scenario: Invalid quote data
- **WHEN** client POSTs with missing required fields
- **THEN** system returns 400 BadRequest
- **AND** error describes which field is invalid

### Requirement: Azure Blob Storage Integration
The system SHALL upload quote documents to Azure Blob Storage and track references.

#### Scenario: Document upload success
- **WHEN** user uploads document with quote
- **THEN** document is stored in blob storage
- **AND** quote references blob URI
- **AND** GUID-based filename is used

## Acceptance Criteria
- [ ] All three requirements implemented
- [ ] All scenarios pass integration tests
- [ ] API documented in Swagger/OpenAPI
- [ ] Managed identity permissions validated
```

#### Creating Specs for Existing Features

If you have existing features without specs:

1. **Review** existing code and documentation
2. **Extract** current behavior as requirements
3. **Write** scenarios based on actual usage
4. **Create** `spec.md` in `openspec/specs/[capability]/`
5. **Add** design.md if there are important architectural decisions

#### Updating Specs with Changes

When implementing a feature via OpenSpec change:

1. **Create** delta spec in `openspec/changes/[change-id]/specs/[capability]/spec.md`
2. **Use** `## ADDED|MODIFIED|REMOVED Requirements` sections
3. **After approval**, the archived change merges into `openspec/specs/[capability]/spec.md`

Example delta spec:
```markdown
# Delta for Quote API

## ADDED Requirements

### Requirement: Bulk Quote Operations
The system SHALL support bulk operations for creating multiple quotes in one request.

#### Scenario: Bulk create with valid data
- **WHEN** client POSTs array of 5 quotes to /quotes/bulk
- **THEN** all quotes are created
- **AND** response includes success count and any errors

## MODIFIED Requirements

### Requirement: Quote Retrieval
The system SHALL return a quote by ID **with caching** for improved performance.

#### Scenario: Cached quote retrieval
- **WHEN** client retrieves same quote within 5 minutes
- **THEN** cached result returned within 10ms
- **AND** cache hit is logged for monitoring
```

#### Linking Specs to Tasks

In your `tasks.md`, reference the specs:

```markdown
## 1. Implement Quote API

### Requirement Reference
See `openspec/specs/api/spec.md` - Quote API Specification

- [ ] 1.1 Implement GET /quotes/{id} endpoint (fulfills Quote Retrieval requirement)
- [ ] 1.2 Add blob storage reference tracking (fulfills Blob Storage requirement)
- [ ] 1.3 Write integration tests for all scenarios
- [ ] 1.4 Validate against acceptance criteria
```

#### Benefits of This Approach

✅ **Clear contracts** - Requirements explicitly define expected behavior  
✅ **Testable** - Scenarios provide test cases  
✅ **Traceable** - Tasks can reference specific requirements  
✅ **Auditable** - Changes documented as deltas  
✅ **Maintainable** - Specs evolve as features grow  
✅ **Reusable** - Specs become reference architecture

---

Only create separate documentation files for:

1. **Complex Integration Guides** (> 50 lines)
   - Example: `docs/Azure_Front_Door_Integration_Guide.md`
   - Step-by-step instructions with PowerShell/CLI commands
   - Troubleshooting section

2. **Architecture Deep-Dives** (> 100 lines)
   - Example: `docs/Architecture_Details.md`
   - Detailed component interactions
   - Network diagrams with explanations
   - Security architecture

3. **Operational Runbooks**
   - Example: `docs/Disaster_Recovery_Procedures.md`
   - Emergency procedures
   - Incident response guides

4. **Historical Documentation** (after OpenSpec archival)
   - Example: `docs/Archived_Changes/Archive_2025-10-30_add-feature.md`
   - Archived change documentation
   - Legacy migration guides

---

## 🔄 Documentation Maintenance Rules

### When Code Changes, Update Documentation

**AI Agent Rules:**

1. **Before making code changes:**
   - Read existing documentation to understand context
   - Check `openspec/specs/` for current capabilities
   - Identify which documentation will be affected

2. **When creating new features:**
   - Create OpenSpec change proposal in `openspec/changes/[change-id]/`
   - Update README with high-level feature description
   - Do NOT create implementation guides (belongs in proposal.md/tasks.md)

3. **When modifying existing features:**
   - Update relevant `openspec/specs/` capability if approved change is implemented
   - Create delta specifications in OpenSpec change folder first
   - Update README only if user-visible changes

4. **When refactoring:**
   - Update architecture section if structure changes
   - Update folder structure in README if files move
   - Create OpenSpec proposal if this is an architectural change
   - Keep old documentation until refactor is complete, then remove

5. **When deprecating:**
   - Mark deprecated sections clearly
   - Provide migration path
   - Remove after grace period

6. **After completing OpenSpec changes:**
   - Verify all tasks in tasks.md are marked complete
   - Run `openspec validate [change-id] --strict` to confirm structure
   - After deployment, archive with `openspec archive [change-id] --yes`
   - Review all documentation for accuracy
   - Remove any duplicate or outdated information

---

## 🚫 Documentation Anti-Patterns to Avoid

### ❌ DO NOT:

1. **Create multiple READMEs for the same content**
   - Bad: `/README.md`, `/docs/README.md`, `/terragrunt/README.md` all describing the same project
   - Good: One comprehensive `/README.md` with links to module-specific READMEs

2. **Duplicate information across files**
   - Bad: Architecture explained in both README and separate architecture doc
   - Good: High-level in README, detailed in `/docs/Architecture_Details.md`

3. **Create documentation "just in case"**
   - Bad: Creating `/docs/Future_Plans.md` before implementation
   - Good: Document what exists now, update when features are added

4. **Leave outdated documentation**
   - Bad: README still mentions deleted production environment
   - Good: Remove or update documentation immediately when code changes

5. **Create overly granular documentation**
   - Bad: Separate file for each Terraform module's 10-line explanation
   - Good: One comprehensive guide covering all modules

6. **Use unclear file names**
   - Bad: `docs/notes.md`, `docs/stuff.md`, `docs/temp.md`
   - Good: `docs/Azure_Front_Door_Integration.md`, `docs/Migration_Guide.md`

7. **❌ Add extra files to OpenSpec change folders**
   - Bad: Adding `COMPLETION_SUMMARY.md`, `IMPLEMENTATION_PLAN.md`, `PHASE_*.md` to `openspec/changes/[change-id]/`
   - Good: Keep change folders minimal with ONLY: proposal.md, tasks.md, design.md (optional), STATUS.md (if complex), and specs/
   - **Why**: OpenSpec archival expects a specific structure; extra files cause confusion during archival and reduce auditability

8. **❌ Create status/progress files in change folders**
   - Bad: `IMPLEMENTATION_STARTED.md`, `DEPLOYMENT_READINESS_REPORT.md` in change folders
   - Good: Track progress in `tasks.md` with completion checkmarks; create `STATUS.md` only at 25%+ milestones for complex features

9. **❌ Mix implementation guides with OpenSpec specs**
   - Bad: Creating `LOCAL_TESTING_GUIDE.md` or `OPENSPEC_UPDATE.md` in change folders
   - Good: Implementation details go in proposal.md/design.md; guides go in `/docs/` after archival if needed

---

## ✅ AI Agent Checklist

Before committing documentation changes, verify:

- [ ] README.md is the primary documentation source
- [ ] No duplicate information across multiple files
- [ ] Deep-dive docs are truly necessary (>50 lines of detailed content)
- [ ] All code changes are reflected in documentation
- [ ] File names are clear and descriptive
- [ ] Links between documents work correctly
- [ ] Folder structure in README matches actual structure
- [ ] No outdated references to deleted features/files
- [ ] Examples are tested and accurate
- [ ] Formatting is consistent (Markdown standards)
- [ ] OpenSpec change folders contain ONLY: proposal.md, tasks.md, design.md (optional), STATUS.md (if needed), and specs/
- [ ] No extra progress or phase files in change folders
- [ ] OpenSpec specs are up-to-date with completed features

---

## 📂 Example Structure

### Good Documentation Structure ✅

```
/
├── README.md                          # Complete project guide
├── docs/
│   ├── Azure_Front_Door_Integration.md    # Deep-dive: Complex setup
│   ├── Architecture_Details.md            # Deep-dive: Detailed architecture
│   ├── Migration_Guide_v1_to_v2.md       # Deep-dive: Major version upgrade
│   └── Troubleshooting.md                 # Deep-dive: Common issues
├── openspec/
│   ├── project.md                         # Project conventions
│   ├── specs/
│   │   ├── auth/
│   │   │   ├── spec.md                    # Current auth spec
│   │   │   └── design.md                  # Auth design patterns
│   │   └── api/
│   │       └── spec.md                    # Current API spec
│   └── changes/
│       ├── add-2fa/
│       │   ├── proposal.md                # Change proposal
│       │   ├── tasks.md                   # Tasks checklist
│       │   └── specs/
│       │       └── auth/
│       │           └── spec.md            # Delta: ADDED 2FA requirements
│       └── archive/
│           └── 2025-01-15-add-2fa/       # Archived completed changes
├── terragrunt/
│   ├── modules/
│   │   └── [module folders - no individual READMEs unless standalone]
│   └── poc/
│       └── README.md (optional)
└── app/
    └── README.md (optional)
```

### Bad Documentation Structure ❌

```
/
├── README.md
├── docs/
│   ├── README.md                      # ❌ Duplicate
│   ├── overview.md                    # ❌ Should be in root README
│   ├── quick-start.md                 # ❌ Should be in root README
│   ├── notes.md                       # ❌ Unclear purpose
│   └── temp.md                        # ❌ Temporary files don't belong
├── openspec/changes/1.3.1-local-testing/
│   ├── proposal.md                    # ✅ Correct
│   ├── tasks.md                       # ✅ Correct
│   ├── specs/                         # ✅ Correct
│   ├── COMPLETION_SUMMARY.md          # ❌ Violates OpenSpec
│   ├── IMPLEMENTATION_PLAN.md         # ❌ Violates OpenSpec
│   ├── LOCAL_TESTING_GUIDE.md         # ❌ Violates OpenSpec
│   ├── PHASE_1_RESULTS.md             # ❌ Violates OpenSpec
│   ├── PHASE_2_RESULTS.md             # ❌ Violates OpenSpec
│   └── DEPLOYMENT_READINESS_REPORT.md # ❌ Violates OpenSpec
```

**Why the 1.3.1 folder is wrong:**
- Extra files (COMPLETION_SUMMARY.md, PHASE_*.md, etc.) violate OpenSpec's minimal structure
- These create confusion during archival and reduce auditability
- Progress should be tracked in `tasks.md` checkmarks
- Complex feature status can use `STATUS.md` (25%+ milestones), but not multiple phase reports

---

## 🎯 Migration Process for Existing Documentation

When consolidating documentation:

1. **Audit Current State**
   - List all documentation files
   - Identify duplicate content
   - Check OpenSpec change folders for violations

2. **Create Comprehensive README**
   - Consolidate general information
   - Add high-level architecture
   - Include quick start and configuration
   - Add links to OpenSpec specs and /docs/ deep-dives

3. **Review OpenSpec Structure**
   - Ensure `openspec/specs/` contains current truth
   - Ensure `openspec/changes/` folders contain ONLY approved files
   - Remove extra files from change folders (move to archive or delete)

4. **Keep Only Essential Deep-Dives**
   - Integration guides for complex setups
   - Detailed architecture (if >100 lines)
   - Troubleshooting guides

5. **Update References**
   - Fix all internal links
   - Link README to OpenSpec specs
   - Update file paths in code comments
   - Update CI/CD documentation references

6. **Archive Completed Changes**
   - For finished features, run `openspec archive [change-id] --yes`
   - Verify specs are properly merged into `openspec/specs/`
   - Keep archived changes for historical reference

---

## 📚 Documentation Templates

### README Template

See the "README.md Requirements" section above for the complete template structure.

### Deep-Dive Document Template

```markdown
# [Specific Topic] - Detailed Guide

> **Related:** [Link to relevant README section]

## Purpose

[Why this document exists - what problem it solves]

## Prerequisites

- [Required knowledge]
- [Required tools]
- [Required access]

## Overview

[High-level explanation of the topic]

## Detailed Instructions

### Step 1: [Action]
[Detailed explanation with commands/code]

### Step 2: [Action]
[Detailed explanation with commands/code]

## Troubleshooting

### Issue: [Common Problem]
**Symptoms:** [How to identify]
**Solution:** [How to fix]

## References

- [External documentation]
- [Related internal docs]

---

**Last Updated:** [Date]
**Maintained By:** [Team/Person]
```

---

## 🔍 Review Process

When reviewing documentation PRs, check:

1. **Necessity** - Is new documentation truly needed?
2. **Location** - Is content in the right place (README vs /docs/ vs openspec/)?
3. **Completeness** - Does it follow the template?
4. **Accuracy** - Is technical content correct?
5. **Clarity** - Can a new team member understand it?
6. **Links** - Do all internal links work?
7. **OpenSpec Compliance** - Do change folders follow minimal structure?
8. **Maintenance** - Is there a clear owner/update schedule?

---

## 📊 Success Metrics

Good documentation should:

- ✅ Enable a new team member to deploy the project in < 30 minutes
- ✅ Answer common questions without external help
- ✅ Stay up-to-date with code changes
- ✅ Be searchable and easy to navigate
- ✅ Provide troubleshooting for common issues
- ✅ Have clear navigation to OpenSpec specs and deep-dives

---

**Last Updated:** October 30, 2025  
**Version:** 2.0 (OpenSpec-aligned)
