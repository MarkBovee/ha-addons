# Mark Bovee's Home Assistant Add-ons

Custom Home Assistant Supervisor add-ons for energy, battery, EV, and heating control.

## Main Add-ons

| Add-on | Purpose |
| --- | --- |
| `Battery API` | Stable SAJ battery control adapter over SAJ cloud API or HA-backed Modbus |
| `Battery Manager` | Price-driven schedule generation and live discharge/charge adjustments |
| `Energy Prices` | Nord Pool import/export price curves and derived pricing |
| `Water Heater Scheduler` | Price-based domestic hot water control |
| `Charge Amps - EV Charger Monitor` | Charge Amps monitoring and control |

## Battery Stack

Battery automation is split on purpose.

- `Battery API` owns inverter communication, provider differences, normalized entities, and schedule apply
- `Battery Manager` owns strategy, price analysis, heuristics, and live schedule regeneration
- Contract between both stays stable through MQTT topic `battery_api/text/schedule/set` and normalized `battery_api_*` entities

This split lets SAJ cloud API and local Modbus run behind same external interface.

## Repository Layout

```text
ha-addons/
├── battery-api/
├── battery-manager/
├── charge-amps-monitor/
├── energy-prices/
├── water-heater-scheduler/
├── docs/
├── shared/
├── run_addon.py
├── sync_shared.py
└── repository.json
```

`shared/` at repo root is source of truth for common Python modules. Add-ons keep their own copies for Docker builds.

After editing root `shared/`, run:

```bash
python sync_shared.py
```

`run_addon.py` also syncs shared code automatically before local runs.

## Install In Home Assistant

1. Open `Settings -> Add-ons -> Add-on Store`.
2. Open repository menu.
3. Add `https://github.com/MarkBovee/ha-addons`.
4. Install required add-ons.

## Recommended Order

For battery automation:

1. Install `Energy Prices`
2. Install `Battery API`
3. Install `Battery Manager`

For EV-aware battery control, add `Charge Amps - EV Charger Monitor`.

## Per Add-on Docs

- [battery-api/README.md](battery-api/README.md)
- [battery-manager/README.md](battery-manager/README.md)
- [energy-prices/README.md](energy-prices/README.md)
- [water-heater-scheduler/README.md](water-heater-scheduler/README.md)
- [charge-amps-monitor/README.md](charge-amps-monitor/README.md)

Background docs:

- [docs/addon-suite-plan.md](docs/addon-suite-plan.md)
- [docs/battery-optimizer-addon.md](docs/battery-optimizer-addon.md)

## Local Development

List add-ons:

```bash
python run_addon.py --list
```

Run one add-on:

```bash
python run_addon.py --addon battery-api
python run_addon.py --addon battery-manager --once
```

Initialize local env file:

```bash
python run_addon.py --addon battery-api --init-env
```

## Notes

- Home Assistant add-on metadata lives in each add-on `config.yaml`
- Repo-level `repository.json` is registry metadata, not runtime source of truth
- Some older docs still existed around `Battery Optimizer`; current production battery stack is `Battery API` + `Battery Manager`

## License

MIT. See [LICENSE](LICENSE).
