# Battery Optimizer Note

`Battery Optimizer` is legacy naming from an earlier design phase.

It is not the current add-on name and not the current architecture.

## Current Replacement

The old single-add-on idea was split into two add-ons:

- `Battery API`: inverter communication layer
- `Battery Manager`: strategy and schedule generation layer

## Why Split

- Provider switching belongs in adapter layer, not strategy layer
- Dashboards and automations need one stable contract
- Live heuristics and price logic should evolve without touching inverter transport code
- Modbus and SAJ cloud API can sit behind same external interface

## Current References

- [../battery-api/README.md](../battery-api/README.md)
- [../battery-manager/README.md](../battery-manager/README.md)
- [addon-suite-plan.md](addon-suite-plan.md)

Treat any older `Battery Optimizer` wording elsewhere as historical context only.
