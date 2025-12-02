# Proposal: Add Water Heater Scheduler Add-on

**Version:** 2.0  
**Status:** 0% - Planning  
**Created:** 2025-12-02  

## Why

The water heater scheduling logic currently lives in the NetDaemon C# codebase (`WaterHeater.cs`). This creates a tight coupling to the NetDaemon runtime and makes it harder to:
- Deploy independently of other NetDaemon apps
- Debug and test in isolation
- Share with users who don't run NetDaemon

Migrating to a standalone Home Assistant add-on aligns with our strategy of modular, single-purpose add-ons that can be installed and configured independently.

## What Changes

| Aspect | Before | After |
|--------|--------|-------|
| Runtime | NetDaemon C# app | Python Home Assistant add-on |
| Price Data | `IPriceHelper` from NetDaemon | Read from `sensor.ep_price_import` attributes (energy-prices add-on) |
| Configuration | Hardcoded in C# | YAML config via add-on UI |
| State Persistence | `AppStateManager` file | Local JSON state file |
| Status Display | `input_text.heating_schedule_status` | Same (compatible) |

## Benefits

1. **Independent deployment** - Install/update without affecting other automations
2. **Consistent architecture** - Same patterns as energy-prices and battery-api add-ons
3. **Easier debugging** - Python with structured logging, local testing via `run_addon.py`
4. **User configurability** - All parameters exposed in add-on UI (night window, temperatures, legionella day)

## Dependencies

- **energy-prices add-on** - Required for price data via `sensor.ep_price_import` with `price_curve` attribute
- **Home Assistant water_heater entity** - Target entity to control (e.g., heat pump domestic hot water)

## Risk Assessment

| Risk | Mitigation |
|------|------------|
| Price data format changes | Use same entity/attribute contract as energy-prices spec |
| Missing tomorrow's prices | Gracefully degrade to today-only scheduling (like NetDaemon version) |
| Water heater entity unavailable | Log error, skip cycle, retry on next interval |

## Success Criteria

- [ ] All core behaviors from `WaterHeater.cs` implemented
- [ ] Night/day program selection based on price curves
- [ ] Legionella protection cycle on configured day
- [ ] Bath mode auto-disable when temperature threshold reached
- [ ] Status entity updates compatible with existing dashboards
- [ ] Local testing works via `run_addon.py --addon water-heater-scheduler`
