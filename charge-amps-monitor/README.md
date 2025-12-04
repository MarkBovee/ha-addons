# Charge Amps EV Charger Monitor

Monitor Charge Amps EV charger status and create Home Assistant entities.

## Overview

This addon connects to the Charge Amps API (my.charge.space) to monitor your EV charger and automatically creates Home Assistant entities for:
- Charging status (on/off)
- Total consumption (kWh)
- Current power (W)
- Voltage and current readings
- Charger online status
- And more...

## Features

- **Automatic Entity Creation**: Creates Home Assistant entities on startup
- **Periodic Updates**: Configurable update interval (default: 1 minute)
- **Secure Authentication**: Uses Charge Amps API with JWT token management
- **Comprehensive Monitoring**: Tracks charging status, power, consumption, and more
- **Price-Aware Scheduling**: Automatically schedules charging during cheapest electricity periods
- **Standalone & HEMS Modes**: Operate autonomously or integrate with external energy management
- **UI-Managed Settings**: All configuration through Home Assistant addon UI

## Operation Modes

The addon supports two operation modes:

### Standalone Mode (Default)

In standalone mode, the addon autonomously analyzes electricity prices and schedules charging during the cheapest periods.

**Features:**
- Reads price data from an energy price sensor (e.g., from energy-prices addon)
- Selects top X unique price levels for charging (configurable)
- Price threshold filtering - excludes slots above a maximum price
- Pushes charging schedules directly to the Charge Amps API

**Configuration:**
```yaml
operation_mode: "standalone"
automation_enabled: true
price_sensor_entity: "sensor.energy_prices_price_import"
top_x_charge_count: 16  # Number of unique price levels to include
price_threshold: 0.25   # Max EUR/kWh - slots above this are excluded
```

### HEMS Mode (External Control)

In HEMS (Home Energy Management System) mode, the addon receives charging schedules from an external system via MQTT.

**Features:**
- Subscribes to MQTT topics for schedule commands
- Validates and applies externally-provided schedules
- Publishes charger status for HEMS consumption
- Prepares for integration with battery-optimizer or other orchestrators

**MQTT Topics:**
- `hems/charge-amps/{connector_id}/schedule/set` - Receive schedule
- `hems/charge-amps/{connector_id}/schedule/clear` - Clear schedule
- `hems/charge-amps/{connector_id}/status` - Published status

**Configuration:**
```yaml
operation_mode: "hems"
# price_threshold is ignored in HEMS mode
```

**Example schedule payload:**
```json
{
  "periods": [
    {"start": "2025-01-15T02:00:00", "end": "2025-01-15T04:00:00"},
    {"start": "2025-01-15T14:00:00", "end": "2025-01-15T15:30:00"}
  ],
  "expires_at": "2025-01-15T23:59:59",
  "source_id": "battery-optimizer"
}
```

## Installation

### Method 1: Custom Repository (Recommended)

1. Add this repository to Home Assistant Supervisor:
   - Go to **Settings** > **Add-ons** > **Add-on Store**
   - Click the three-dot menu (⋮) in the top right
   - Select **Repositories**
   - Add repository URL: `https://github.com/MarkBovee/ha-addons`
   - Click **Add**

2. Install the addon:
   - The addon should appear in the store
   - Click **Charge Amps - EV Charger Monitor**
   - Click **Install**
   - Configure settings (see Configuration below)
   - Click **Start**

### Method 2: Local Installation

1. Copy the addon directory to your Home Assistant `/addons` folder:
   ```bash
   cp -r charge-amps-monitor /config/addons/
   ```

2. In Home Assistant:
   - Go to **Settings** > **Add-ons** > **Add-on Store**
   - Click **Check for updates**
   - Find **Charge Amps - EV Charger Monitor** under **Local add-ons**
   - Click **Install**
   - Configure and start

## Configuration

Configure the addon through the Home Assistant UI:

1. Go to **Settings** > **Add-ons** > **Charge Amps - EV Charger Monitor**
2. Click **Configuration**
3. Enter your settings:

### Basic Settings
   - **Email**: Your Charge Amps account email
   - **Password**: Your Charge Amps account password
   - **Host Name**: API hostname (default: `my.charge.space`)
   - **Base URL**: API base URL (default: `https://my.charge.space`)
   - **Update Interval**: Update interval in minutes (default: `1`)

### Operation Mode
   - **Operation Mode**: `standalone` (default) or `hems`
     - `standalone`: Internal price-based scheduling
     - `hems`: External schedule control via MQTT

### Standalone Mode Options
   - **Enable Automation**: Toggle to allow the add-on to schedule charging windows
   - **Price Sensor Entity**: Home Assistant entity that exposes price per kWh
   - **Top X Charge Count**: Number of unique price levels to select (default: `16`)
     - *Note*: This selects price *levels*, not slot count. Multiple slots at the same price = more charging time.
   - **Price Threshold**: Maximum price in EUR/kWh (default: `0.25`)
     - Slots above this price are excluded from scheduling
     - Set to `1.0` to effectively disable threshold filtering
   - **Max Current Per Phase**: Safety limit for active charging (default `16` amps)
   - **Connector IDs**: Comma-separated Charge Amps connector IDs to control (default `1`)

4. Click **Save**
5. Start the addon

## Created Entities

The addon creates the following Home Assistant entities (all prefixed with `ca_`):

### Basic Entities
- `input_boolean.ca_charger_charging` - Charging status (on/off)
- `input_number.ca_charger_total_consumption_kwh` - Total consumption
- `input_number.ca_charger_current_power_w` - Current power

### Sensor Entities
- `sensor.ca_charger_status` - Charge point status
- `sensor.ca_charger_power_kw` - Current power in kW
- `sensor.ca_charger_voltage` - Average voltage
- `sensor.ca_charger_current` - Average current
- `sensor.ca_charger_connector_mode` - Connector mode
- `sensor.ca_charger_ocpp_status` - OCPP status
- `sensor.ca_charger_error_code` - Error code (if any)

### Automation Sensors
- `sensor.ca_schedule_status` - Current schedule state (idle, active, error)
- `sensor.ca_schedule_source` - Schedule source: `standalone`, `hems`, or `none`
- `sensor.ca_next_start` - Next scheduled charge start time
- `sensor.ca_next_end` - Next scheduled charge end time
- `sensor.ca_schedule_error` - Last scheduling error (if any)
- `sensor.ca_hems_last_command` - Timestamp of last HEMS command (diagnostic)

### Binary Sensors
- `binary_sensor.ca_charger_online` - Charger online status
- `binary_sensor.ca_charger_connector_enabled` - Connector enabled state
- `binary_sensor.ca_price_threshold_active` - Indicates if price threshold excluded any slots

### Text Entities
- `input_text.ca_charger_name` - Charge point name
- `input_text.ca_charger_serial` - Serial number

## Local Development

### Prerequisites

- Python 3.12+
- VS Code with Remote Containers extension (optional)

### Quick Start (Recommended)

The easiest way to run the addon locally is using the provided debug scripts:

1. **Install dependencies:**
   ```bash
   cd charge-amps-monitor
   pip install -r requirements.txt
   ```

2. **Create a `.env` file:**
   ```bash
   cp .env.example .env
   ```
   Then edit `.env` and fill in your credentials:
   - `CHARGER_EMAIL` - Your Charge Amps account email
   - `CHARGER_PASSWORD` - Your Charge Amps account password
   - `HA_API_TOKEN` - Your Home Assistant API token (Long-Lived Access Token)
   - `HA_API_URL` - Home Assistant API URL (default: `http://localhost:8123/api`)
    - Optional automation overrides:
       - `CHARGER_AUTOMATION_ENABLED`
       - `CHARGER_PRICE_SENSOR_ENTITY`
       - `CHARGER_REQUIRED_MINUTES_PER_DAY`
       - `CHARGER_EARLIEST_START_HOUR`
       - `CHARGER_LATEST_END_HOUR`
       - `CHARGER_MAX_CURRENT_PER_PHASE`
       - `CHARGER_CONNECTOR_IDS`
       - `CHARGER_SAFETY_MARGIN_MINUTES`

3. **Run the debug script:**
   
   **On Linux/Mac:**
   ```bash
   ./run_local.sh
   ```
   
   **On Windows (PowerShell):**
   ```powershell
   .\run_local.ps1
   ```
   
   **Or directly with Python:**
   ```bash
   python run_local.py
   ```

The debug script will:
- Load environment variables from `.env` file (if present)
- Validate required configuration
- Display a configuration summary
- Run the application with proper error handling

### Using Dev Container

1. Open the project in VS Code
2. When prompted, click **Reopen in Container**
3. The container will build and install dependencies
4. Create a `.env` file or set environment variables
5. Run: `python run_local.py` or `./run_local.sh`

### Manual Testing (Advanced)

If you prefer to set environment variables manually:

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Set environment variables:**
   
   **On Linux/Mac:**
   ```bash
   export CHARGER_EMAIL="your-email@example.com"
   export CHARGER_PASSWORD="your-password"
   export CHARGER_HOST_NAME="my.charge.space"
   export CHARGER_BASE_URL="https://my.charge.space"
   export CHARGER_UPDATE_INTERVAL="1"
   export CHARGER_AUTOMATION_ENABLED="false"
   export CHARGER_PRICE_SENSOR_ENTITY="sensor.ep_price_import"
   export CHARGER_REQUIRED_MINUTES_PER_DAY="240"
   export CHARGER_EARLIEST_START_HOUR="0"
   export CHARGER_LATEST_END_HOUR="8"
   export CHARGER_MAX_CURRENT_PER_PHASE="16"
   export CHARGER_CONNECTOR_IDS="1"
   export CHARGER_SAFETY_MARGIN_MINUTES="15"
   export HA_API_TOKEN="your-ha-token"
   export HA_API_URL="http://localhost:8123/api"
   ```
   
   **On Windows (PowerShell):**
   ```powershell
   $env:CHARGER_EMAIL="your-email@example.com"
   $env:CHARGER_PASSWORD="your-password"
   $env:CHARGER_HOST_NAME="my.charge.space"
   $env:CHARGER_BASE_URL="https://my.charge.space"
   $env:CHARGER_UPDATE_INTERVAL="1"
   $env:CHARGER_AUTOMATION_ENABLED="false"
   $env:CHARGER_PRICE_SENSOR_ENTITY="sensor.ep_price_import"
   $env:CHARGER_REQUIRED_MINUTES_PER_DAY="240"
   $env:CHARGER_EARLIEST_START_HOUR="0"
   $env:CHARGER_LATEST_END_HOUR="8"
   $env:CHARGER_MAX_CURRENT_PER_PHASE="16"
   $env:CHARGER_CONNECTOR_IDS="1"
   $env:CHARGER_SAFETY_MARGIN_MINUTES="15"
   $env:HA_API_TOKEN="your-ha-token"
   $env:HA_API_URL="http://localhost:8123/api"
   ```

3. **Run the application:**
   ```bash
   python3 -m app.main
   ```

## Architecture

```
charge-amps-monitor/
├── config.yaml          # Addon metadata and options schema
├── Dockerfile           # Container definition
├── run.sh              # Entry script
├── requirements.txt    # Python dependencies
├── app/
│   ├── __init__.py
│   ├── main.py         # Main application loop
│   ├── charger_api.py  # Charge Amps API client
│   └── models.py       # Data models
└── README.md           # This file
```

## API Integration

The addon uses the Charge Amps API:

1. **Authentication**: POST to `/api/auth/login` with email, password, hostName
2. **Get Charge Points**: POST to `/api/users/chargepoints/owned?expand=ocppConfig`
3. **Token Management**: Automatically refreshes JWT tokens before expiration

## Troubleshooting

### Addon won't start

- Check logs: **Settings** > **Add-ons** > **Charge Amps - EV Charger Monitor** > **Log**
- Verify configuration: Ensure email and password are correct
- Check network connectivity to Charge Amps API

### Entities not appearing

- Wait a few minutes for initial update
- Check addon logs for errors
- Verify Home Assistant API token is valid
- Ensure addon has started successfully

### Authentication errors

- Verify email and password are correct
- Check that host_name matches your Charge Amps account
- Review logs for detailed error messages

## License

This project is licensed under the MIT License - see the [LICENSE](../LICENSE) file for details.

