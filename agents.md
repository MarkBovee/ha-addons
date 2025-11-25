<!-- OPENSPEC:START -->
# OpenSpec Instructions

These instructions are for AI assistants working in this project.

Always open `@/openspec/AGENTS.md` when the request:
- Mentions planning or proposals (words like proposal, spec, change, plan)
- Introduces new capabilities, breaking changes, architecture shifts, or big performance/security work
- Sounds ambiguous and you need the authoritative spec before coding

Use `@/openspec/AGENTS.md` to learn:
- How to create and apply change proposals
- Spec format and conventions
- Project structure and guidelines

Keep this managed block so 'openspec update' can refresh the instructions.

<!-- OPENSPEC:END -->

# AI Agent Guidelines

Use this document whenever you plan, review, or implement changes in this repository. It captures the conventions we already follow plus industry guidance on `agents.md` structure, PR hygiene, and documentation style drawn from the [agentsmd.io best practices](https://agentsmd.io/agents-md-best-practices?utm_source=openai).

---

## Repository Overview

- `charge-amps-monitor/` – Home Assistant add-on written in Python; talks to the Charge Amps cloud via the `ChargerApi` client (`app/charger_api.py`) and pushes entities into Home Assistant through REST calls in `app/main.py`.
- `repository.json`, root `README.md`, and per-addon `README.md` files describe how Home Assistant discovers and installs each add-on. Keep them accurate whenever you add or rename files.
- Future add-ons should live in peer directories, each with its own `app/`, `config.yaml`, and docs. Add nested `agents.md` files inside each addon if they require rules that differ from the items below (hierarchical `agents.md` files keep guidance scoped as the repo grows).

---

## Coding Standards

### Python add-ons

1. **Target runtime**: Python 3.12+. Align new dependencies with `requirements.txt` and pin exact versions.
2. **Structure**: Place networking logic in `app/charger_api.py` (extend `ChargerApi` or helpers there) and Home Assistant orchestration in `app/main.py`.
3. **Logging**: Use the configured `logging` logger and prefer structured messages (`logger.info("Fetched %s charge points", count)`).
4. **HTTP**: Reuse the existing `requests.Session` in `ChargerApi` so authentication headers and retries stay centralized.
5. **Models**: Extend or add data models in `app/models.py` instead of passing bare dicts around.
6. **Graceful shutdowns**: Honor the `shutdown_flag` and signal handlers defined in `app/main.py`; long-running loops must check the flag each iteration.

### Commenting & documentation

- Python: keep module, function, and class docstrings concise and actionable. Prefer doctrings over inline comments unless clarifying tricky logic.
- .NET or C# utilities (if/when added): use XML documentation comments that include `summary`, `param`, `returns`, and `exception` tags, e.g.:

  ```csharp
  /// <summary>
  /// Describe the side effect or value returned.
  /// </summary>
  /// <param name="cancellationToken">How cancellation propagates.</param>
  /// <returns>The processed payload.</returns>
  public Task<ChargerResult> ProcessAsync(CancellationToken cancellationToken) { ... }
  ```

- Keep comments accurate—update them whenever code changes. Avoid restating what the code already makes obvious.

### YAML & metadata

- Ensure `config.yaml` values match add-on reality (name, slug, version, supported architectures).
- When you add new configuration options, document both the `options` defaults and the `schema` types, then reference them in the add-on README.

---

## API & Home Assistant Integration

1. `ChargerApi.authenticate()` posts to `https://my.charge.space/api/auth/login` and stores the JWT token plus expiration buffer. Always call `_ensure_authenticated()` before issuing new API requests.
2. `ChargerApi.get_charge_points()` posts to `/api/users/chargepoints/owned?expand=ocppConfig`. Parse responses into `ChargePoint` / `Connector` model instances via their `from_dict` helpers instead of reimplementing parsing.
3. Entity management happens through Home Assistant’s Supervisor REST API:
   - `create_or_update_entity()` issues authenticated POSTs to `/api/states/{entity_id}`.
   - `delete_entity()` removes stale IDs before recreating them; extend the `old_entities` list when renaming.
4. Whenever you add new Home Assistant entities, ensure friendly names, units, icons, and prefixes follow the existing `ca_` conventions so dashboards remain consistent.

---

## Configuration, Secrets, and Local Debugging

- Local scripts (`run_local.py`, `run_local.ps1`, `run_local.sh`) expect a `.env` file with Charge Amps and Home Assistant credentials. Never commit `.env` or other secrets; rely on `.env.example` when documenting new variables.
- Environment variables should fall back to safe defaults (`HA_API_URL`, `HA_API_TOKEN`, etc.) like in `get_ha_api_url()` and `get_ha_api_token()`. Mirror that pattern for new settings.
- Validate inputs early (e.g., ensure intervals are positive integers) and fail fast with clear log messages.

---

## Workflow Expectations

### Bundling changes

- Keep pull requests scoped: group related edits (e.g., API change + entity update) in the same PR, but avoid mixing unrelated add-ons or refactors.
- Update every artifact affected by the change—code, `README.md`, `CHANGELOG.md`, and `config.yaml`—in one bundle so reviewers see the full context.

### Commit / PR checklist

- `feat(scope): short explanation` commit style keeps history legible.
- Before opening a PR:
  - Run local tests or scripts (`python run_local.py`) with representative credentials.
  - Lint or format Python files (e.g., `ruff`, `black`) if you introduce new code.
  - Verify Home Assistant entity creation end-to-end in a dev instance when possible.
  - Confirm documentation and sample configs match the new behavior.
  - Remove leftover debug prints and commented-out code.

### Reviews & automation

- Provide concrete examples in the PR description: highlight files to follow when adding new sensors (`app/main.py` entity helpers, `app/models.py` parsing logic).
- Mention any new environment variables or secrets clearly so deployers can update their setups.

---

## Extending This Document

- Add directory-specific `agents.md` files whenever an add-on needs custom rules. Reference this root document from those files for shared rules.
- As new languages enter the repo, append language-specific sections (Go, TypeScript, etc.) including their lint/test workflows and documentation standards.

Following these guardrails keeps AI agents and humans aligned, ensures clean documentation (including XML comments where applicable), and helps us ship tightly scoped, well-tested Home Assistant add-ons.***

