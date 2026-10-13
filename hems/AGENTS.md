# HEMS (hems/)

Instructions for AI agents working on HEMS v2. The repository-wide rules in `../AGENTS.md` apply (Home Assistant entities and services are the only integration boundary, branch and commit conventions, never commit to `master`). Where HEMS deliberately deviates, `../docs/hems/intake-decisions.md` is the record; read it first. Ignore `openspec/` for HEMS work (owner's instruction).

## Layout

| Path | What it is |
|---|---|
| `hems/core/` | Hardware-agnostic planning core (`hems/core/hems/*.py`), no Home Assistant imports, no vendor names. Source of truth. |
| `custom_components/hems/` | The Home Assistant integration (dry-run planner, sensors, config flow). `engine/` inside it is a **generated copy** of `hems/core`; never edit it. |
| `scripts/sync_hems_core.py` | Regenerates `custom_components/hems/engine` from the core (`--check` verifies). |
| `scripts/hems_collect.py`, `scripts/hems_replay.py` | Read-only data collector and the replay of recorded days. |
| `tests/hems_ha/` | Integration tests (need the pinned Home Assistant test plugin, see below). |
| `hems/tests/` | Tests of the deploy script. |
| `hems/deploy.py` | Deploys `custom_components/hems` to the local Home Assistant server. |

## Rules that are easy to break

- Edit `hems/core`, then run `python3 scripts/sync_hems_core.py`. A core test fails when the engine copy is stale.
- The integration only plans (dry-run). It must not call a device service. Writing to a device is a separate, explicitly approved change.
- Every function gets a short intent docstring, tests included. Verify with an AST scan before finishing.
- Prices: the percentage Zonnebonus applies only in daylight and for a positive price (both switchable); the energy-prices add-on code applies it always, do not copy that.
- The minimum profit margin (`min_profit_margin`, default 0.10 EUR/kWh) is a planner threshold, never a cost. Replay and sensors report cash.
- Entity ids are derived from the English entity names (`sensor.hems_battery_action`, `binary_sensor.hems_tomorrow_prices_available`); keep the English name stable.
- Weather (Open-Meteo) requests carry coordinates rounded to 0.01 degrees. Keep it that way.

## Tests

```bash
cd hems/core && python3 -m pytest                 # core, replay, price/Nord Pool/forecast logic
python3 -m pytest hems/tests                      # deploy script
python3 scripts/sync_hems_core.py --check         # engine copy current?
# integration tests: a venv with the plugin that pins the server's Home Assistant version (2026.9.4)
python3 -m venv .venv-ha && .venv-ha/bin/pip install "pytest-homeassistant-custom-component==0.13.367"
.venv-ha/bin/python -m pytest tests/hems_ha       # the recorder_mock fixture must be requested before hass
python3 scripts/hems_replay.py                    # replay on the local recorded days (needs the gitignored data)
```

## Deploying to the Home Assistant server

Deploy only when the user asks for it for this change; approval for one deploy does not cover the next. Never push, and never deploy from a dirty or failing tree.

```bash
python3 hems/deploy.py --dry-run     # shows target, files, and changes nothing
python3 hems/deploy.py               # runs the checks, backs up, deploys, verifies by sha256
python3 hems/deploy.py --batch       # key only, never prompts (for unattended use)
python3 hems/deploy.py --restart     # additionally validates the HA config and restarts HA after a confirmation
```

What it does: runs the core tests and the engine-sync check; on the server it archives the current `custom_components/hems` to `/config/.hems-backup/` (three kept), unpacks the new copy next to it and swaps the directory, so a broken transfer leaves the running copy alone; then it compares sha256 of every file. Restoring a backup: `tar -C /config/custom_components -xzf /config/.hems-backup/<file>.tar.gz`, then restart HA.

Configuration comes from `.env` in the repository root (gitignored): `HA_HOST`, `HA_SSH_USER`, and optionally `HA_SSH_KEY` (path to a private key). `HA_API_URL` and `HA_API_TOKEN` are only needed for `--restart`. The target defaults to `/config` on the server (the SSH add-on mounts the HA configuration there).

### Credentials: what an agent may and may not do

- Never use a password to log in: no `sshpass`, `expect`, scripted password input, or a library call that takes `HA_SSH_PASSWORD` / `HA_PASSWORD`. Do not add such a feature to `deploy.py`; the tests assert that a password never reaches the target or the ssh command line.
- Do not print `.env` values. When you need to know what is configured, list the key names only (`sed -E 's/=.*/=<set>/' .env`).
- Authentication is done by the person (typing the password at the ssh prompt) or by a key the person has authorised. An agent may run `python3 hems/deploy.py` when the user has approved the deploy and a key or agent is set up; otherwise hand the user the command to run themselves. If a password prompt appears, stop and ask the user to enter it.
- Setting up a key is the user's action, once:

```bash
ssh-keygen -t ed25519 -f ~/.ssh/ha_hems -C "hems deploy"      # add a passphrase and use ssh-agent if you prefer
ssh-copy-id -i ~/.ssh/ha_hems.pub <HA_SSH_USER>@<HA_HOST>       # asks for the password once, by you
echo 'HA_SSH_KEY=~/.ssh/ha_hems' >> .env
```

  A key without passphrase gives whoever holds the file the same access as the SSH add-on; keep it dedicated and out of the repository. With a working key the plaintext passwords in `.env` are not needed and can be removed.

### After a deploy

1. Restart Home Assistant (user approval; or `--restart`). A new or changed integration is only loaded after a restart.
2. First time only: Settings, Devices & services, Add integration, HEMS; pick the entities (the table in `../docs/hems/install.md`).
3. Verify read-only through the Home Assistant MCP tools or REST: `sensor.hems_status` is `ok`, `sensor.hems_battery_action` has a `reason`, `binary_sensor.hems_tomorrow_prices_available` matches whether Nord Pool has published, and `/config/hems/decision_trace.jsonl` gains a line per quarter.
4. Read the HA log for `custom_components.hems` errors; a failed Nord Pool or Open-Meteo fetch is a warning and the plan continues on the fallbacks.
