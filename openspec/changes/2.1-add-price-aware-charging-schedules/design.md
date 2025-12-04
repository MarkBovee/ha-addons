# Design: Price-Aware Charge Amps Scheduling (Version 2.1)

## Context

The Charge Amps add-on authenticates with `my.charge.space`, surfaces telemetry, and optionally publishes Home Assistant entities through REST or MQTT discovery. Users still have to open the Charge Amps mobile app to configure “smart charging” schedules. Because Nord Pool prices shift daily, the manual workflow defeats the purpose of the `energy-prices` add-on. This change lets the add-on ingest the price curve, select the optimal charging window, and write it back to the charger via the `smartChargingSchedules` API that we already captured in HAR traces.

## Goals

- Create a deterministic daily plan that charges for a user-defined duration during the cheapest contiguous interval between configured earliest/latest hours.
- Keep automation safe: allow users to toggle it off/on, restore their original schedule, and reconcile hourly if an external actor edits the plan.
- Provide transparency via HA helper entities and a manual `force_refresh` service so people understand when/why a schedule changed.

## Non-Goals

- Fine-grained SOC control or per-minute current modulation — the scope is limited to setting fixed `maxCurrent` blocks per connector.
- Bidirectional communication with the vehicle or wallbox beyond the Smart Charging endpoints already exposed by Charge Amps.
- Predicting beyond 48 hours. We will only plan “next day” windows once tomorrow’s prices exist.

## Decisions

1. **Price source** – Default to `sensor.ep_price_import` but allow any HA entity id as long as it exposes a `price_curve` attribute containing `[{start,end,price}]` entries. This reuses the energy-prices contract and avoids duplicating Nord Pool calls.
2. **Window selection algorithm** – Implement a sliding window tied to 15-minute buckets (matching Nord Pool granularity). We compute the sum of prices for each contiguous block that meets the required duration and choose the minimum-cost block that also meets earliest/latest guardrails. Ties prefer the earliest start time to keep behavior predictable.
3. **Timezone handling** – Read HA’s timezone from the Supervisor info endpoint. All calculations happen in local time, then converted to seconds-from-week-start for the Charge Amps API (`from`/`to` offsets). This ensures DST shifts produce correct UTC startOfSchedule anchors.
4. **Schedule identity** – Persist a JSON file containing the schedule id, connector id, window start/end, and price hash. When reconciling we compare the current API payload to that hash to determine drift and limit DELETE/PUT to automation-owned schedules.
5. **Observability** – Publish `sensor.ca_charging_schedule_status`, `sensor.ca_next_charge_start`, and `sensor.ca_next_charge_end` via MQTT discovery (with unique IDs) plus expose a `charge_amps.force_schedule_refresh` service that re-runs the planner immediately.

## Risks / Trade-offs

- **API rate limits** – Charge Amps may throttle frequent schedule updates; we mitigate by planning once per day (after tomorrow’s prices) and limiting hourly checks to lightweight comparisons unless drift is detected.
- **Multiple connectors** – Some installations have more than one connector per charge point. Our first iteration will accept one connector id per add-on instance; supporting multi-connector orchestration would require per-connector planning, which is deferred.
- **User overrides** – If the user edits the schedule in the Charge Amps app while automation is on, our next hourly reconciliation will overwrite it. We document this clearly and provide the automation toggle to pause the feature.

## Migration Plan

1. Ship new configuration schema and helper sensors without enabling automation by default. Collect feedback while automation toggle is off.
2. Add the price planner + schedule writer behind the toggle. Provide detailed logs and documentation for early adopters.
3. Once validated, consider enabling automation by default for new installs (still opt-in for existing users) and evaluate multi-connector support.

## Open Questions

- Do we need to support different durations for weekdays vs weekends?
- Should we expose an optional “minimum savings threshold” (skip automation if cheapest block is only marginally cheaper)?
- How should we handle existing smart charging schedules that the user wants to keep alongside ours — do we mark ours with a specific name/metadata to avoid collisions?
