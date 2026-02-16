# Home Assistant Add-ons Agent Team (GitHub Copilot)

This workspace uses a multi-agent setup for Home Assistant add-on development and maintenance.

## Available Agents

- `Orchestrator` - Coordinates the full development and release flow
- `Planner` - Creates implementation plans with acceptance criteria
- `Python Developer` - Implements Python code for add-ons following repository conventions
- `HA Debugger` - Connects to live HA instance to diagnose issues (sensors, logs, MQTT)
- `Tester` - Validates add-ons through local testing and verification
- `Reviewer` - Performs code quality review against repository standards
- `Docs Writer` - Updates documentation when behavior or configuration changes
- `Add-on Packager` - Manages Docker, config.yaml, versioning, and CHANGELOG
- `OpenSpec Manager` - Handles OpenSpec change proposals for new features
- `Shared Module Manager` - Manages shared Python modules and syncs across add-ons

## Model Strategy

- `GPT-5.3-Codex`: Orchestrator, Python Developer, HA Debugger
- `GPT-5 mini`: Planner, Tester, Reviewer, Docs Writer, Add-on Packager, OpenSpec Manager, Shared Module Manager

## Execution Mode (Latency-Aware)

- **Default mode: direct-first.** For most bug fixes and HA diagnostics, use local tools directly
  (workspace search, file reads, terminal, HA API calls) instead of delegating to subagents.
- **Use subagents for complex or parallel work only** (multi-lane features, broad audits,
  or explicit user request).
- **Timeout fallback:** if a delegated lane is slow or times out, continue in direct-first mode
  instead of repeating the same delegation pattern.

## Standard Development Flows

### New Feature Flow
1. Planning (`Planner`)
2. OpenSpec proposal (`OpenSpec Manager`) - if new capability or breaking change
3. Implementation (`Python Developer`)
4. Shared module sync (`Shared Module Manager`) - if shared modules modified
5. Testing (`Tester`)
6. Code review (`Reviewer`)
7. Documentation (`Docs Writer`)
8. Packaging (`Add-on Packager`)
9. OpenSpec archival (`OpenSpec Manager`) - if proposal created
10. Final summary (`Orchestrator`)

### Bug Fix Flow (Fast Track)
1. Quick scope (`Planner`)
2. Live diagnosis (`HA Debugger`) - if HA instance access available
3. Implementation (`Python Developer`)
4. Testing (`Tester`)
5. Quick review (`Reviewer`)
6. CHANGELOG update (`Docs Writer`)
7. Version bump (`Add-on Packager`)

### Shared Module Update Flow
1. Plan changes (`Planner`)
2. Implement in root shared/ (`Python Developer`)
3. Sync to all add-ons (`Shared Module Manager`)
4. Regression testing all add-ons (`Tester`)
5. Review (`Reviewer`)

### Live HA Debugging Flow
1. Define symptom (`Planner`)
2. Collect diagnostics (`HA Debugger`) - entity states, logs, MQTT, API responses
3. Analyze root cause (`HA Debugger`)
4. Implement fix (`Python Developer`)
5. Verify in HA instance (`HA Debugger`)

## Agent Team Emulation (Copilot)

Use this mode when you want behavior closest to Claude agent teams.

### 1. Team Kickoff (Lead Only)
- `Orchestrator` creates a shared todo list with 5-6 atomic tasks per teammate lane
- Every task title starts with lane ownership: `[Python Developer] implement price calculation`
- Dependencies are encoded in task ordering; blocked tasks stay `not-started`

### 2. Delegate-First Execution
- `Orchestrator` stays coordination-only until all lane outputs return
- Independent lanes can run in parallel via subagents when latency is acceptable
- Dependent work remains sequential with explicit handoff notes

### 3. Teammate Contract
- Each teammate returns: decisions, changed files, risks, and next actions
- If a teammate is blocked, it must return a concrete unblock request

### 4. Merge and Quality Gates
- `Orchestrator` synthesizes lane results and resolves conflicts
- Mandatory gates:
  - `Tester` pass/fail with commands
  - `Reviewer` must-fix status
  - `Shared Module Manager` sync validation (if applicable)
  - `Add-on Packager` release artifact validation
- Failed gates re-enter the fix loop: `Python Developer` → `Tester` → `Reviewer`

### 5. Team Closeout
- `Orchestrator` marks all tasks completed
- Publishes final Go/No-Go with open risks

### Parallel Execution Strategy

| Lane Type | Agents | Parallelization |
|-----------|--------|----------------|
| Planning | Planner, OpenSpec Manager | Can run in parallel with code analysis |
| Implementation | Python Developer, Shared Module Manager | Sequential (implement → sync) |
| Validation | Tester, HA Debugger | Sequential (test → debug if needed) |
| Quality | Reviewer | After testing completes |
| Release | Docs Writer, Add-on Packager | Can run in parallel if clear contract |

## Home Assistant Specific Patterns

### Add-on Structure
Every add-on follows standardized layout:
- `app/main.py` - Orchestration and main loop
- `app/models.py` - Data models with from_dict()/to_dict()
- `app/[name]_api.py` - External API clients
- `app/[feature].py` - Business logic modules
- `shared/` - Copy of root shared/ (never edit directly)
- `config.yaml` - HA metadata and option schema
- `Dockerfile` - Alpine-based container build
- `requirements.txt` - Pinned Python dependencies

### Entity Management
- Prefix all entities with add-on identifier: `ca_`, `ep_`, `bm_`, `ba_`, `wh_`
- Prefer MQTT Discovery over REST API (provides unique_id, UI management)
- Store rich data in entity attributes (price curves, schedules, metadata)

### Shared Modules
- Root `shared/` is the source of truth - NEVER edit `<addon>/shared/` directly
- After editing root `shared/`, run `python sync_shared.py`
- All add-ons must be regression tested after shared module changes
- `Shared Module Manager` enforces this workflow

### Local Development
```bash
# List available add-ons
python run_addon.py --list

# Initialize .env file
python run_addon.py --addon energy-prices --init-env

# Run single iteration (fast test)
python run_addon.py --addon energy-prices --once

# Run continuously (integration test)
python run_addon.py --addon energy-prices
```

### HA Debugger Access Requirements
To use `HA Debugger` with live Home Assistant instance:

**Environment Variables:**
```bash
SUPERVISOR_TOKEN=your_supervisor_token
HA_URL=http://supervisor  # or your HA URL
# Optional for MQTT debugging:
MQTT_HOST=your_mqtt_broker
MQTT_USER=your_mqtt_user
MQTT_PASS=your_mqtt_pass
```

**Capabilities:**
- Read entity states and attributes via HA REST API
- Get entity history
- Query add-on logs via Supervisor API
- Monitor MQTT messages (if MQTT broker accessible)
- Test external API endpoints (Nord Pool, Charge Amps, SAJ Electric)

## Starter Prompts

Type these to invoke common workflows:

- `/agent-team-emulation` - Full team emulation mode for complex development
- `/complete-dev-cycle` - Complete development lifecycle from planning to release
- `/new-addon-flow` - Create a new add-on from scratch
- `/feature-addition-flow` - Add feature to existing add-on
- `/bugfix-flow` - Fast-track bug fix
- `/debug-live-ha` - Debug live HA instance issues
- `/shared-module-update` - Update shared modules with regression testing
- `/openspec-proposal` - Create OpenSpec change proposal

## Structure

- Agents are defined in `.github/agents/*.agent.md`
- Prompts are defined in `.github/prompts/*.prompt.md`
- Shared workflow and coding rules are in `.github/instructions/*.instructions.md`
- OpenSpec instructions in `openspec/AGENTS.md`
- `Orchestrator` invokes subagents with `runSubagent` tool

## Quality Gates

Every delivery must pass:
- [ ] Planning includes explicit acceptance criteria
- [ ] OpenSpec proposal created for new capabilities/breaking changes
- [ ] Code implements to plan
- [ ] All tests pass with documented commands
- [ ] Code review approved (no must-fix issues)
- [ ] Shared module changes synced to all add-ons
- [ ] Documentation updated (README, CHANGELOG)
- [ ] Version bumped correctly (semantic versioning)
- [ ] Packaging validated (Dockerfile, config.yaml, requirements.txt)

## Branch Strategy (Enforced)

Never work on `master` directly:

| Change Type | Branch Pattern | Example |
|-------------|---------------|---------|
| New feature / breaking change | `feature/[name]` | `feature/add-solar-forecast` |
| Bug fix | `fix/[name]` | `fix/price-calculation` |
| Refactor | `refactor/[name]` | `refactor/api-client` |
| Documentation | `docs/[name]` | `docs/update-readme` |

New features and breaking changes also require OpenSpec change proposals.

## Integration Points

### External APIs
- **Nord Pool**: Day-ahead electricity prices (no auth)
- **Charge Amps Cloud**: EV charger monitoring (JWT auth)
- **SAJ Electric**: Battery inverter control (API key auth)
- **HA Supervisor**: Add-on management and HA API access (supervisor token)

### Add-on Dependencies
- `battery-manager` depends on: `energy-prices`, `charge-amps-monitor`, `battery-api`
- `water-heater-scheduler` depends on: `energy-prices`

### Local Testing Requirements
Each add-on needs specific environment variables (see add-on README for details):
- **energy-prices**: `AREA` (NO1-NO5)
- **charge-amps-monitor**: `CA_API_KEY`, `CA_CHARGE_POINT_ID`
- **battery-api**: `SAJ_API_KEY`, `SAJ_PLANT_ID`
- **battery-manager**: Depends on other add-ons' entities
- **water-heater-scheduler**: Depends on energy-prices entities

## Documentation Standards

Follow `.github/instructions/documentation.instructions.md`:
- Single source of truth (one comprehensive README per add-on)
- Always up-to-date (update with every code change)
- No temporary files (`*_REPORT.md`, `*_SUMMARY.md`, `PROGRESS_*.md`)
- OpenSpec specs in `openspec/specs/` (canonical)
- OpenSpec proposals in `openspec/changes/` (temporary until archived)

## Common Scenarios

### Scenario 1: Adding new feature to existing add-on
```
User: Add solar forecast to battery-manager
→ Use: /feature-addition-flow
→ Agents involved: Planner → OpenSpec Manager → Python Developer → Tester → Reviewer → Docs Writer → Add-on Packager
```

### Scenario 2: Debugging entity not updating
```
User: sensor.ep_price_import stuck on unavailable
→ Use: /debug-live-ha
→ Agents involved: Planner → HA Debugger → Python Developer → Tester → HA Debugger (verify)
```

### Scenario 3: Updating shared logging module
```
User: Add structured logging format to all add-ons
→ Use: /shared-module-update
→ Agents involved: Planner → Python Developer → Shared Module Manager → Tester (all add-ons) → Reviewer
```

### Scenario 4: Creating new add-on
```
User: Create vacation-mode add-on for security
→ Use: /new-addon-flow
→ Agents involved: Planner → OpenSpec Manager → Python Developer → Shared Module Manager → Tester → Reviewer → Docs Writer → Add-on Packager
```

## Tips for Effective Agent Usage

1. **Be specific in your request**: Include add-on name, feature description, expected behavior
2. **Use appropriate flow**: Choose the right prompt for your task type
3. **Provide context**: Mention if it's a new capability (needs OpenSpec) or bug fix (fast track)
4. **Enable HA Debugger**: Set environment variables if you need live HA diagnosis
5. **Choose speed when needed**: Ask for direct-first execution when troubleshooting live issues
6. **Trust the process**: Let `Orchestrator` coordinate, don't micromanage individual agents
7. **Review quality gates**: Check that all mandatory gates pass before considering work complete

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Agent not responding | Ensure agent name is spelled correctly (case-sensitive) |
| Missing HA access | Set SUPERVISOR_TOKEN and HA_URL environment variables |
| Shared module sync fails | Check that changes are in root `shared/`, not `<addon>/shared/` |
| Tests failing | Run `python run_addon.py --addon [name] --init-env` to create .env file |
| OpenSpec validation fails | Check folder structure, ensure proposal.md and tasks.md exist |
