# Proposal: Add Battery API Add-on

**Version:** 1.2  
**Status:** 100% — COMPLETE ✅  
**Created:** 2025-11-25  
**Completed:** 2025-11-28  
**PR:** [#9](https://github.com/MarkBovee/ha-addons/pull/9) (merged)

---

## Executive Summary

Create a standalone Home Assistant add-on that communicates with SAJ Electric inverters to expose battery status and control via **Home Assistant entities only**—no REST API endpoints. Users control battery charging/discharging by setting HA entities (power, duration, start time, type), and the add-on watches for changes and applies schedules to the inverter via the SAJ Cloud API.

This separates the battery API layer from the NetDaemon optimization logic, allowing:
- Standalone battery control without NetDaemon
- Simpler debugging of inverter communication issues
- Reusable battery primitives for automations

---

## What's Changing

| Aspect | Before | After |
|--------|--------|-------|
| Battery control | Only via NetDaemon apps | Standalone HA add-on with entity-based control |
| SAJ API access | C# in NetDaemonApps | Python add-on (portable, debuggable) |
| Schedule creation | Complex multi-period strategies | Simple single-period commands + read current schedule |
| Status visibility | Hidden in NetDaemon logs | Dedicated HA sensors (SOC, mode, direction, schedule) |

---

## Benefits

1. **Separation of Concerns** — Battery API communication isolated from optimization logic
2. **Debuggability** — Standalone add-on with clear logs for SAJ API issues
3. **Automation Friendly** — HA entities enable automations without NetDaemon
4. **Simpler Testing** — Test battery API without full NetDaemon stack
5. **Portable** — Python implementation reusable across HA installations

---

## Success Criteria

- [x] Add-on connects to SAJ API and authenticates successfully ✅
- [x] SOC sensor updates every 60 seconds with accurate battery level ✅
- [x] User can trigger a simple charge/discharge via entity controls ✅
- [x] Schedule applied to inverter matches requested parameters (power, duration, time) ✅
- [x] Status entities reflect current inverter state (mode, charge direction) ✅
- [x] All entities have proper `unique_id` via MQTT Discovery ✅

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| SAJ API changes | Medium | High | Port existing C# implementation closely; add API version detection |
| MQTT broker not installed | Medium | Medium | Fallback to REST API entity creation; document MQTT requirement |
| Complex schedule patterns unsupported | Low | Medium | v1 supports 1+1 pattern only; document limitations |
| Token expiry during long operations | Low | Low | Proactive token refresh (existing pattern from C#) |

---

## Implementation Timeline

| Phase | Deliverable | Estimate |
|-------|-------------|----------|
| 1. Scaffold | Add-on structure, config.yaml, Dockerfile | 1h |
| 2. SAJ API Client | Authentication, token management, basic calls | 3h |
| 3. Entity Publishing | MQTT Discovery for sensors + controls | 2h |
| 4. Schedule Application | Single-period charge/discharge via entities | 2h |
| 5. Status Polling | SOC, mode, direction updates | 1h |
| 6. Documentation | README, CHANGELOG, config examples | 1h |

**Total Estimate:** ~10 hours

---

## Key Technical Discovery

**SAJ API Register Mapping (Decoded 2025-11-28):**

Analyzed HAR files to decode the Modbus register addresses used by the SAJ H2 inverter:

| Component | Base Register | Slots |
|-----------|---------------|-------|
| Header (TOU mode) | `0x3647` | 1 |
| Charge periods | `0x3606` | 3 max |
| Discharge periods | `0x361B` | 6 max |

Each slot uses 3 consecutive registers. Pattern generation is now dynamic instead of hardcoded, supporting any combination of 0-3 charges + 0-6 discharges.

See `design.md` for full technical details and Python implementation.

---

## Design Decisions

See `design.md` for technical details on:
- Entity-based control vs REST API
- MQTT Discovery entity types
- SAJ API porting strategy
- **SAJ register mapping and dynamic pattern generation**

---

## References

- NetDaemon Battery API: `NetDaemonApps/Models/Battery/BatteryApi.cs`
- NetDaemon Schedule Service: `NetDaemonApps/Models/Battery/ScheduleApplyService.cs`
- Existing add-on patterns: `energy-prices/`, `charge-amps-monitor/`
- MQTT Discovery: `shared/ha_mqtt_discovery.py`
