---
description: Full multi-agent flow for developing a new Home Assistant add-on from scratch.
agent: Ask
model: GPT-5.3-Codex
---

Use `Orchestrator` to create a new Home Assistant add-on with complete development flow.

Requirements:
- Understand the add-on purpose and requirements.
- Create OpenSpec proposal (mandatory for new add-ons).
- Implement add-on structure (app/, config.yaml, Dockerfile, README).
- Configure MQTT Discovery entities or HA API integration.
- Test locally with run_addon.py.
- Create documentation and CHANGELOG.
- Package for release (versioning, Docker, config validation).

Execution protocol:
1. `Planner` - Define scope, entities, config options, external APIs, acceptance criteria.
2. `OpenSpec Manager` - Create change proposal with capability specifications.
3. `Python Developer` - Implement add-on structure, main loop, API clients, entity management.
4. `Shared Module Manager` - Sync shared modules to new add-on.
5. `Tester` - Validate local runs, entity creation, API integration.
6. `Reviewer` - Check code quality, patterns, error handling.
7. `Docs Writer` - Create README, CHANGELOG.
8. `Add-on Packager` - Validate Dockerfile, config.yaml, requirements.txt, version.
9. `OpenSpec Manager` - Archive change proposal.

Respond with:
1) Add-on created: [slug], [name]
2) Entities published: [list]
3) Configuration options: [list]
4) Test results: [pass/fail with commands]
5) Files created: [list]
6) Next steps: [deployment, testing in HA]
