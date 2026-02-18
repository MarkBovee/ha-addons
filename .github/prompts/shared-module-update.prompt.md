---
description: Update shared modules safely across add-ons.
agent: Ask
model: GPT-5.3-Codex
---

Use `Orchestrator`, delegate to `Shared Module Manager` if root `shared/` changes are involved.

Checklist:
1. Edit root `shared/` only.
2. Sync to add-ons.
3. Run targeted regression checks.
4. Report impacted add-ons.
