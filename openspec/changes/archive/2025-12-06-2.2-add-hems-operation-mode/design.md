# Design: HEMS Operation Mode

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                    charge-amps-monitor                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────────┐      ┌──────────────────────────────────┐    │
│  │   Config     │      │     Mode Router                   │    │
│  │              │─────▶│                                   │    │
│  │ operation_   │      │  standalone ──▶ PriceSlotAnalyzer │    │
│  │   mode       │      │                     │             │    │
│  │              │      │                     ▼             │    │
│  │ price_       │      │              ThresholdFilter      │    │
│  │   threshold  │      │                     │             │    │
│  └──────────────┘      │                     ▼             │    │
│                        │              UniquePriceSelector  │    │
│                        │                     │             │    │
│                        │       hems ───▶ HEMSHandler ──────┤    │
│                        │                     │             │    │
│                        └─────────────────────┼─────────────┘    │
│                                              │                  │
│                                              ▼                  │
│                        ┌─────────────────────────────────┐      │
│                        │   ChargingAutomationCoordinator │      │
│                        │                                 │      │
│                        │   - Applies schedule to charger │      │
│                        │   - Publishes HA entities       │      │
│                        │   - Publishes HEMS status       │      │
│                        └─────────────────────────────────┘      │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
              ┌───────────────────────────────┐
              │         MQTT Broker           │
              │      (core-mosquitto)         │
              ├───────────────────────────────┤
              │ Topics:                       │
              │ - hems/charge-amps/1/schedule/set   │
              │ - hems/charge-amps/1/schedule/clear │
              │ - hems/charge-amps/1/status         │
              └───────────────────────────────┘
                              │
                              ▼
              ┌───────────────────────────────┐
              │      Future HEMS System       │
              │   (external orchestrator)     │
              └───────────────────────────────┘
```

## Unique Price Selection Algorithm

### Current Behavior (to be replaced)
```python
# Selects top X slots by price (may have duplicates)
sorted_slots = sorted(all_slots, key=lambda s: s.price)
selected = sorted_slots[:top_x_count]
```

### New Behavior
```python
def select_by_unique_prices(slots, top_x_levels, price_threshold):
    # Step 1: Filter by threshold
    eligible = [s for s in slots if s.price <= price_threshold]
    
    # Step 2: Group by unique price
    price_groups = defaultdict(list)
    for slot in eligible:
        price_groups[slot.price].append(slot)
    
    # Step 3: Sort price levels
    sorted_prices = sorted(price_groups.keys())
    
    # Step 4: Select top X unique price levels
    selected_prices = sorted_prices[:top_x_levels]
    
    # Step 5: Flatten - include ALL slots at selected price levels
    selected_slots = []
    for price in selected_prices:
        selected_slots.extend(price_groups[price])
    
    # Step 6: Sort by time for schedule
    return sorted(selected_slots, key=lambda s: s.start)
```

### Example

Given prices (EUR/kWh):
```
00:00-00:15: 0.08   ─┐
00:15-00:30: 0.08   ─┤ Price level 1 (€0.08) - 3 slots
00:30-00:45: 0.08   ─┘
00:45-01:00: 0.10   ─┐ Price level 2 (€0.10) - 2 slots
01:00-01:15: 0.10   ─┘
01:15-01:30: 0.12   ── Price level 3 (€0.12) - 1 slot
...
06:00-06:15: 0.28   ── Price level 17 (€0.28) - EXCLUDED (above threshold)
```

With `top_x_charge_count: 3` and `price_threshold: 0.25`:
- Selected: 6 slots (all slots at price levels 1, 2, 3)
- Not 3 slots as before

## HEMS Message Flow

### Schedule Set
```
HEMS System                    charge-amps-monitor              Charge Amps API
     │                                  │                              │
     │ MQTT: schedule/set               │                              │
     │ {periods: [...]}                 │                              │
     │─────────────────────────────────▶│                              │
     │                                  │ Validate payload             │
     │                                  │ Convert to schedule          │
     │                                  │                              │
     │                                  │ PUT /smartChargingSchedules  │
     │                                  │─────────────────────────────▶│
     │                                  │                              │
     │                                  │◀─────────────────────────────│
     │                                  │ Store schedule_source=hems   │
     │                                  │                              │
     │ MQTT: status                     │                              │
     │ {schedule_source: "hems", ...}   │                              │
     │◀─────────────────────────────────│                              │
```

### Mode Switch (HEMS → Standalone)
```
User changes config              charge-amps-monitor              Charge Amps API
     │                                  │                              │
     │ Config reload                    │                              │
     │ operation_mode: standalone       │                              │
     │─────────────────────────────────▶│                              │
     │                                  │ Clear HEMS subscriptions     │
     │                                  │ Delete current schedule      │
     │                                  │─────────────────────────────▶│
     │                                  │                              │
     │                                  │ Initialize PriceSlotAnalyzer │
     │                                  │ Analyze prices               │
     │                                  │ Apply new standalone schedule│
     │                                  │─────────────────────────────▶│
```

## Entity Structure

### New Entities

| Entity ID | Type | HEMS Mode | Standalone Mode |
|-----------|------|-----------|-----------------|
| `sensor.ca_schedule_source` | sensor | `hems` | `standalone` |
| `sensor.ca_hems_last_command` | sensor | timestamp | `unavailable` |
| `binary_sensor.ca_price_threshold_active` | binary_sensor | `off` | `on` if slots filtered |

### Modified Entities

| Entity ID | Change |
|-----------|--------|
| `sensor.ca_charging_schedule_status` | Add `schedule_source` attribute |

## Configuration Schema

```yaml
schema:
  # Existing...
  
  # New: Operation mode
  operation_mode: list(standalone|hems)?  # default: standalone
  
  # New: Price threshold (standalone mode)
  price_threshold: float?  # default: 0.25, range 0.0-1.0
```

## Error Handling

| Scenario | Behavior |
|----------|----------|
| Invalid HEMS JSON | Log error, ignore message, keep previous state |
| HEMS schedule in past | Log warning, apply only future periods |
| No slots below threshold | Set status to "no_eligible_slots", don't charge |
| MQTT disconnect (HEMS mode) | Keep last schedule, expose `hems_connected: false` |
| Mode switch mid-charge | Complete current 15-min slot, then switch |

## Backward Compatibility

- Default `operation_mode: standalone` maintains current behavior
- Existing configs without new fields work unchanged
- `top_x_charge_count` semantic change (slots → unique prices) may select more slots
  - Document in CHANGELOG as behavior change
  - Users wanting exact slot count can set threshold very high
