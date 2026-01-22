# Comparison Plan: Legacy C# vs. New Python Battery Manager

## Goal
Verify that the new Python `battery-manager` produces identical logic decisions and log output format as the currently running legacy C# NetDaemon app.

## Prerequisites
- Legacy app (`c6a2317c_netdaemon5`) is running in **Production** (controlling the battery).
- New Python app will run locally in **Dry Run** mode (logging only, no MQTT commands).

## Phase 1: Context Verification
1.  **Check Configuration**: Ensure `config.yaml` (Python) matches `appsettings.json` (C#) thresholds:
    *   Top X discharge hours.
    *   Min/Max power settings.
    *   SOC safety thresholds (min, conservative).
2.  **Verify Sensors**: Confirm both apps are reading the same source entities for:
    *   Grid Power (`sensor.battery_api_grid_power`)
    *   Battery Power (`sensor.battery_api_battery_power` / `current_power`)
    *   Temperature (`sensor.weather_forecast_temperature`)

## Phase 2: Parallel Execution
1.  **Start Python Add-on (Dry Run)**:
    *   Modify `defaults` in `main.py` or set env var via `run_addon.ps1` to force `dry_run: true`.
    *   Run: `.\run_addon.ps1 -addon battery-manager`
    *   *Note*: This ensures we generate "what if" logs without interfering with the battery.

2.  **Fetch Live Legacy Logs**:
    *   Use the `fetch_ha_logs.py` script logic (re-created) to pull the last 100 lines from the legacy addon.

## Phase 3: Log Analysis
Compare the following specific log events from both streams:

### 1. Status Heartbeat
*   **Legacy**: `Discharging Active (600W) 🥶 7°C | Monitoring active period...`
*   **Python**: `Discharging Active | Mode: adaptive 🥶 7°C` (or similar)
*   **Check**: Are the icons identical? Is the temperature reading identical?

### 2. Adaptive Logic Math
*   **Legacy**: `Adaptive power adjustment: 600W -> 800W`
*   **Python**: `Power adjustment applied: 800W (+200W)`
*   **Check**: Do both calculate the same target power (e.g., 800W) given the same grid/load conditions? allowed slightly different timestamps, but the *logic* (Grid + Current = New) must hold.

### 3. Price Range Classification
*   **Legacy**: `Adaptive Range: €0.272 - €0.374/kWh`
*   **Python**: `Range: adaptive €0.272-€0.374`
*   **Check**: Do they identify the same price windows?

## Phase 4: Sign-off
*   If logic matches > 95% (minor timing differences expected), approve for deployment.
*   If major deviations found (e.g., Python wants to charge while C# wants to discharge), pause and fix `heuristics` in `config.yaml`.
