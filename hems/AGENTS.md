# HEMS (hems/)

Instructions for AI agents working on HEMS v2. The repository-wide rules in `../AGENTS.md` apply (Home Assistant entities and services are the only integration boundary, branch and commit conventions, never commit to `master`). Where HEMS deliberately deviates, `../docs/hems/intake-decisions.md` is the record; read it first. Ignore `openspec/` for HEMS work (owner's instruction).

## Layout

| Path | What it is |
|---|---|
| `hems/core/` | Hardware-agnostic planning core (`hems/core/hems/*.py`), no Home Assistant imports, no vendor names. Source of truth. |
| `custom_components/hems/` | The Home Assistant integration (dry-run planner, sensors, config flow). `engine/` inside it is a **generated copy** of `hems/core`; never edit it. |
| `scripts/sync_hems_core.py` | Regenerates `custom_components/hems/engine` from the core (`--check` verifies). |
| `scripts/hems_collect.py`, `scripts/hems_replay.py` | Read-only data collector and the replay of recorded days. |
| `scripts/hems_trace.py` | Reads the decision logs (`/config/hems/*.jsonl`): `--pull`, `tail`, `show`, `why`, `diff`, `events`. See `../docs/hems/install.md`. |
| `hems/core/hems/windows.py` | Read-only analysis of sell windows: detection (two cost bases), which charge feeds which sale, status per window, kWh sold outside any window. |
| `hems/core/hems/heater.py` | The switchable water heater module: plans the daily heating runs with the water-heater add-on's rule (cheapest night and day window) for the load forecast; it never controls the heater. |
| `hems/core/hems/ev.py` | The switchable EV module: one planner with a deadline schedule, a price threshold and PV surplus as priced terms, plus the setpoint with minimum on/off times. Proposes only; the HA layer reads the entities and never writes to the charger. See `../docs/hems/ev-module-plan.md`. |
| `hems/core/hems/terminal.py` | Value of energy kept past the horizon from the typical peak of the last days (replay-tested, not wired into the live integration: the 12-day simulation showed little gain, see `../docs/hems/observations/margin-study-2026-10-17.md`). |
| `hems/core/hems/decision_log.py` | What makes a decision followable: plan segments, best later opportunities, the compact full-plan record, settings hash. |
| `tests/hems_ha/` | Integration tests (need the pinned Home Assistant test plugin, see below). |
| `hems/tests/` | Tests of the deploy script. |
| `hems/deploy.py` | Deploys `custom_components/hems` to the local Home Assistant server. |

## Rules that are easy to break

- Edit `hems/core`, then run `python3 scripts/sync_hems_core.py`. A core test fails when the engine copy is stale.
- The integration only plans (dry-run). It must not call a device service. The one switch HEMS owns (`switch.hems_ev_force_charge`) changes the plan, not a device. Writing to a device is a separate, explicitly approved change.
- Every function gets a short intent docstring, tests included. Verify with an AST scan before finishing.
- Prices: the percentage Zonnebonus applies only in daylight and for a positive price (both switchable); the energy-prices add-on code applies it always, do not copy that.
- The minimum profit margin (`min_profit_margin`, default 0.10 EUR/kWh) is a planner threshold, never a cost. Replay and sensors report cash.
- Entity ids are set explicitly from the entity key (`sensor.hems_battery_action`, `binary_sensor.hems_tomorrow_prices_available`) because Home Assistant otherwise derives them from the instance language (a Dutch install gets `sensor.hems_batterij_actie`). Keep the keys stable; renaming one breaks dashboards.
- Every decision must stay explainable: the planner keeps the numbers behind each slot (`sell_value`, `buy_cost`, `stored_value`, `reason_code`) and the coordinator logs them. When you add a decision step, add its inputs and outcome to the decision record or to `events.jsonl`, with a test.
- Planner and executor are separate (`hems/core/hems/executor.py`). The planner decides the shape of the day from forecasts; the executor re-checks the live SoC before anything is sent and on every SoC update. Any code that will write to a device must take its power from `Execution.power_w`, never from the plan's command, and the planner and executor share the floor (`battery.floor_fraction`).
- Times in logs and readers always say the day when it is not the plan's first day (`decision_log.when`, `+1d 07:30`): plans run 48 h and an unlabelled 07:30 reads as today.
- The HA log must show the decisions: the integration sets its own logger to INFO at setup (the server runs `logger: default: warning`). Do not move per-cycle lines to DEBUG.
- The planner has one economic objective over the whole horizon. Do not add hour budgets, fixed price ceilings, or "only after X" candidate filters: a rule that silently removes quarters hides a profitable peak (battery-manager missed the morning peak of 2026-10-14 this way, see `docs/hems/intake-decisions.md`). A constraint is a priced term and shows up in the trace with its reason.
- The text that explains a decision must be true: sell value is priced where the kWh lands (import price only while the discharge stays below the house load), and when the marginal comparison does not confirm the choice the reason says "plan-level". `tests/test_two_peaks.py` guards both.
- A reason text is judged on the numbers it prints (rounded to three decimals): `sell 0.313 > keep 0.313` is false, so equal printed numbers get `>=` / `<=` and reversed ones get "plan-level". Every log line carries the `build` that wrote it; check it before calling a line an open bug.
- The executor measures the room left from the moment the SoC value last changed (`Reading.changed_at`), never from the moment of the last repeat of the same value; a limit that rises with the clock flaps.
- Sell windows (`hems/core/hems/windows.py`) are an analysis of the prices and the finished plan, never an input of the planner: no candidate filter, no budget per window, no minimum start SoC (decision of 15 Oct 2026 and its numbers in `docs/hems/intake-decisions.md`, lesson 7). If a preference needs a window it becomes a priced term with the window as the unit of accounting. A test keeps the layer honest: over 48 hours every planned sale lies inside a detected window.
- A state that a user reads must make sense without this code: no bare counts or codes (the plan sensor said `57`, the number of quarters). Say what happens when, in local time and the language of Home Assistant; put the numbers in attributes. Attributes use readable names, not one-letter keys.
- Weather (Open-Meteo) requests carry coordinates rounded to 0.01 degrees. Keep it that way.

## Tests

```bash
cd hems/core && python3 -m pytest                 # core, replay, price/Nord Pool/forecast logic
python3 -m pytest hems/tests                      # deploy script
python3 scripts/sync_hems_core.py --check         # engine copy current?
# integration tests: a venv with the plugin that pins the server's Home Assistant version (2026.10.2)
python3 -m venv .venv-ha && .venv-ha/bin/pip install "pytest-homeassistant-custom-component==0.13.373"
.venv-ha/bin/python -m pytest tests/hems_ha       # the recorder_mock fixture must be requested before hass
python3 scripts/hems_replay.py                    # replay on the local recorded days (needs the gitignored data)
```

## Deploying to the Home Assistant server

Standing approval (Mark, 13 Oct 2026): for test rounds of HEMS an agent may, without asking each time, deploy with `python3 hems/deploy.py --batch`, restart Home Assistant (`--restart --yes`; HA automations are down for 1-5 minutes, add-ons such as battery-manager keep running) and add or reload the HEMS integration through the Home Assistant tools. It covers HEMS in dry-run only: it does not cover enabling any device writes, changing other integrations or add-ons, or pushing. Never deploy from a dirty or failing tree, and tell the user what was deployed afterwards.

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

1. Restart Home Assistant (user approval; or `--restart`). A new or changed integration is only loaded after a restart. `deploy.py --restart --yes` waits until the REST API answers again; after a restart the SoC sensors of battery-api appear a little later, HEMS then reports `no_soc` and replans by itself after 60 seconds.
2. First time only: add the integration, in the UI or through the Home Assistant tools: `ha_set_integration(domain="hems", config={"soc_entity": ..., "battery_power_entity": ..., "battery_power_positive_is_discharging": true, "pv_entity": ..., "grid_entity": ..., "inverter_output_entity": ..., "ev_power_entity": ..., "price_curve_entity": ...})` with the entities from the table in `../docs/hems/install.md`. To start over (for instance after an entity-id change) remove the entry with `ha_remove_helpers_integrations(target=<entry_id>, confirm=True)` and add it again; only ever remove the HEMS entry.
3. Verify read-only through the Home Assistant MCP tools or REST: `sensor.hems_status` is `ok`, `sensor.hems_battery_action` has a `reason`, `binary_sensor.hems_tomorrow_prices_available` matches whether Nord Pool has published, and the logs grow: `python3 scripts/hems_trace.py --pull tail -n 5` shows the latest cycles, `events` the fetches and status changes.
4. Read the HA log for `custom_components.hems`: `python3 scripts/hems_trace.py halog` (REST proxy of the Supervisor, read-only) shows one decision line and the plan tree per quarter, every event, and warnings for a failed Nord Pool or Open-Meteo fetch (the plan continues on the fallbacks), a status other than `ok`, or an executor override. `ha core logs` does not work from the SSH add-on (401), and `HA_API_URL` already ends in `/api`: request `/states/...`, not `/api/states/...`. Mark sees the same lines in Settings, System, Logs.

### Monitoring

A scheduled task (`hems-dry-run-monitoring`, daily 08:26 local, set up by Mark on 13 Oct 2026) reviews the previous day read-only and writes `docs/hems/observations/monitoring/<date>.md`; it ends with a week summary after 20 Oct. It never deploys or writes to Home Assistant.
