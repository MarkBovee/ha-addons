# Proposal: Add Price-Aware Charge Amps Scheduling

**Version:** 2.1  
**Status:** ⏳ DRAFT - 0%  
**Created:** 2025-12-04  
**Completed:** TBD

## Why

Charge Amps owners currently rely on the OEM app to define fixed charging schedules. With highly volatile electricity prices, that static plan causes either missed cheap windows or unnecessary charging during expensive peaks. We already expose detailed Nord Pool prices via the `energy-prices` add-on, but the Charge Amps monitor only publishes telemetry — it never applies those prices to create a dynamic schedule. Users asked for an automated workflow that consumes the price curve, finds the cheapest contiguous window that satisfies their daily energy target, and pushes that schedule to the charger without manual intervention.

## What Changes

| Aspect | Before | After |
|--------|--------|-------|
| Configuration | Only credentials + polling interval | Adds automation toggle, price sensor entity, required minutes per day, earliest start / latest end hour limits, connector + max current overrides |
| Price awareness | Charge Amps add-on ignores price data | Reads `price_curve` from `sensor.ep_price_import` (or user-selected entity) to score every 15‑minute interval in HA’s timezone |
| Scheduling | Users edit schedules in Charge Amps app | Add-on calculates cheapest block once tomorrow’s prices arrive (~14:30 local) and writes it through `/api/smartChargingSchedules` (PUT/DELETE) |
| Reconciliation | No safety net if someone edits the schedule out-of-band | Hourly reconciliation compares the live schedule with the desired plan and re-applies if the charger, user, or API drifts |
| Observability | No insight into automation decisions | Publishes status + `next_start`/`next_end` helper sensors and exposes a `force_refresh` service for manual retries |

## Benefits

1. **Cheapest-energy charging** – Automatically selects the best-priced window within user constraints, reducing overnight charging costs without daily tinkering.
2. **Hands-off reliability** – Hourly reconciliation and clear automation toggles make it easy to pause, resume, or override schedules while ensuring we revert to the intended plan afterward.
3. **Centralized configuration** – All knobs (duration, price entity, amp limit, timezone handling) live in the add-on UI and inherit defaults from our suite, so users no longer bounce between Home Assistant and Charge Amps apps.

## Dependencies

- `energy-prices` add-on (or another HA entity exposing a `price_curve` attribute with 15-minute intervals) – used to rank intervals.
- Home Assistant Supervisor info API to read the configured timezone (fallback to `Europe/Amsterdam`).
- Charge Amps REST API endpoints captured in the HAR files (`/api/smartChargingSchedules/chargepoint/{id}`, PUT `/api/smartChargingSchedules`, DELETE `/api/smartChargingSchedules/{chargePointId}/{connectorId}`).

## Risk Assessment

| Risk | Mitigation |
|------|------------|
| Price curve missing or incomplete when automation runs | Detect missing tomorrow data; delay planning until 96 future intervals exist or fall back to “tonight only” mode with a warning sensor state. |
| Conflicts with user-managed schedules | Store the automation flag + last schedule hash; if users disable automation we immediately delete our schedule and stop hourly reconciliation. |
| Timezone drift between HA and Charge Amps | Always convert 15-minute bucket boundaries from HA timezone to UTC before calling the API and surface conversion errors in the status sensor. |
| API throttling / failures | Wrap PUT/DELETE calls with retries + exponential backoff and surface failures through the `force_refresh` service + status entity so users know action is required. |

## Success Criteria

- [ ] New configuration options appear in `config.yaml` and README with validation (automation toggle, price sensor entity, connector selection, required duration, earliest start/latest end, max current override).
- [ ] Scheduler waits until tomorrow’s price curve is published, selects the cheapest contiguous block covering the required duration within user time limits, and writes that plan through the Charge Amps API.
- [ ] Hourly reconciliation detects drift (missing schedule, unsynced `isSynced`, changed periods) and reapplies the automation schedule when the toggle is enabled.
- [ ] New HA helper sensors (status text + next start/end) and a `charge_amps.force_schedule_refresh` service give users immediate insight and manual control.
- [ ] Unit tests cover price-window selection edge cases (missing data, split across midnight, daylight-savings boundaries) and API client retries.
