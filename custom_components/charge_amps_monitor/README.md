# Charge Amps Monitor Integration

Home Assistant custom integration for monitoring Charge Amps EV chargers.

## Features

- **Automatic Discovery**: Finds all charge points and connectors associated with your Charge Amps account
- **Real-time Monitoring**: Updates at configurable intervals (default: 60 seconds)
- **Per-Connector Sensors**: Individual sensors for each charging connector
- **Device Grouping**: All entities are grouped under their respective charger device

## Installation

### HACS (Recommended)

1. Add this repository as a custom repository in HACS
2. Search for "Charge Amps Monitor" and install
3. Restart Home Assistant
4. Go to Settings → Devices & Services → Add Integration → Charge Amps Monitor

### Manual Installation

1. Copy the `charge_amps_monitor` folder to your `custom_components` directory
2. Restart Home Assistant
3. Go to Settings → Devices & Services → Add Integration → Charge Amps Monitor

## Configuration

The integration uses a config flow wizard:

### Step 1: Credentials
- **Email**: Your Charge Amps account email
- **Password**: Your Charge Amps account password

### Step 2: Advanced Settings (Optional)
- **API Host**: API hostname (default: my.charge.space)
- **Base URL**: Full API URL (default: https://my.charge.space)
- **Update Interval**: How often to poll for updates in seconds (default: 60, min: 10, max: 3600)

## Entities

### Per Charger
| Entity | Type | Description |
|--------|------|-------------|
| Charger Status | Sensor | Online/Offline/Error status |
| Online | Binary Sensor | Connectivity status |

### Per Connector
| Entity | Type | Description |
|--------|------|-------------|
| Power | Sensor | Current charging power (W) |
| Total Consumption | Sensor | Lifetime energy consumption (kWh) |
| Voltage L1/L2/L3 | Sensor | Per-phase voltage (V) |
| Current L1/L2/L3 | Sensor | Per-phase current (A) |
| Connector Status | Sensor | OCPP status (Available, Charging, etc.) |
| Charging | Binary Sensor | Whether actively charging |

## OCPP Status Values

| Code | Status |
|------|--------|
| 1 | Available |
| 2 | Preparing |
| 3 | Charging |
| 4 | Suspended EV |
| 5 | Suspended EVSE |
| 6 | Finishing |
| 7 | Reserved |
| 8 | Unavailable |
| 9 | Faulted |

## Options Flow

After installation, you can modify the update interval through the integration options:

1. Go to Settings → Devices & Services
2. Find "Charge Amps Monitor"
3. Click "Configure"
4. Adjust the update interval as needed

## Troubleshooting

### Authentication Errors
- Verify your email and password are correct
- Check that you can log in at https://my.charge.space

### No Data / Sensors Unavailable
- Check Home Assistant logs for API errors
- Ensure your charger is online and connected to the internet
- Try reducing the update interval if you're getting rate limited

### Missing Chargers
- The integration discovers all chargers associated with your account
- If a charger is missing, verify it's properly registered in your Charge Amps account

## License

This project is licensed under the MIT License.
