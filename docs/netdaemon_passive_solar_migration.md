# NetDaemonApps Passive Solar Strategy Migration Guide

This document summarizes the successful "Passive Solar Charging" strategy implemented in `NetDaemonApps` and how it maps to the new `battery-strategy-optimizer` add-on.

## The Strategy: "Passive Gap"

The core finding is that forcing the inverter to a specific charge rate often results in grid interaction (importing or exporting) due to control loops. The "Passive Gap" strategy instead tells the inverter to **do nothing** (0W charge) for a short period, allowing its internal MPPT logic to self-consume excess solar naturally.

### Mechanism

1.  **Detection**: The system monitors `sensor.power_production` (Solar) and `sensor.power_net` (Grid).
2.  **Trigger**: When excess solar is detected, a special schedule is command is sent.
3.  **Command**: The MQTT schedule sent is:
    - **Interval 1 (Now + 1 min)**: 0W Charge (The "Gap")
    - **Interval 2 (Future)**: Discharge (to ensure inverter doesn't idle indefinitely if solar drops)
4.  **Result**: The inverter sees the 0W limit and directs all PV production to the battery (up to its BMS limit) minus house load, effectively "soaking up" the sun without logic fighting the grid meter.

## Configuration & Logic (NetDaemonApps Source)

### Entry Conditions (Triggers)
The system enters Passive Mode if **ANY** of these are true:
*   **Instant Surplus**: Net Export > 1000W
*   **Sustained Surplus**: Net Export > 500W for > 5 minutes

### Exit Conditions
The system exits Passive Mode if **ANY** of these are true:
*   **Grid Import**: Net Import > 200W for > 3 minutes
*   **Low Solar**: PV Production < 200W

### Inverter Command
*   **Topic**: `battery_api/text/schedule/set`
*   **Payload Model**: `0W` charge for first timeslot.

## Porting to HA-Addons (`battery-strategy-optimizer`)

This logic has been incorporated into the OpenSpec for the new add-on (Version 2.3).

### New Component: `solar_monitor.py`
*   **Responsibility**: Polls HA sensors every minute.
*   **Logic**: Implements the Entry/Exit hysteresis described above.
*   **Output**: Sets internal state `passive_solar_active = True/False`.

### New Component: `gap_scheduler.py`
*   **Responsibility**: Generates the specific JSON payload when `passive_solar_active` is True.
*   **Priority**: High. Overrides price-based charging schedules during daylight hours.

### Reference Files
*   **NetDaemon**: `Apps/Energy/SolarMonitor.cs` (Logic), `Apps/Energy/InverterController.cs` (Command)
*   **HA-Addon Spec**: `openspec/changes/2.3-add-battery-strategy-optimizer/specs/battery-strategy/spec.md`

---
*Created: 2026-02-02*
