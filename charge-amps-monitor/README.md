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
- **UI-Managed Settings**: All configuration through Home Assistant addon UI

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

   - **Email**: Your Charge Amps account email
   - **Password**: Your Charge Amps account password
   - **Host Name**: API hostname (default: `my.charge.space`)
   - **Base URL**: API base URL (default: `https://my.charge.space`)
   - **Update Interval**: Update interval in minutes (default: `1`)

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

### Binary Sensors
- `binary_sensor.ca_charger_online` - Charger online status
- `binary_sensor.ca_charger_connector_enabled` - Connector enabled state

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

