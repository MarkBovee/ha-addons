# Custom Components (Home Assistant Integrations)

This folder contains **Home Assistant integrations** (custom components) that provide a better UI experience than add-ons.

## Why Integrations?

| Feature | Add-on | Integration |
|---------|--------|-------------|
| Entity pickers (selectors) | ❌ | ✅ |
| Multi-step config wizard | ❌ | ✅ |
| Options flow (reconfigure live) | ❌ | ✅ |
| Device grouping in UI | ❌ | ✅ |
| Native HA service calls | ❌ | ✅ |

## Available Integrations

### Water Heater Scheduler

Schedules domestic hot water heating based on electricity prices.

**Features:**
- Entity selector for water heater and price sensor
- Temperature presets (eco, comfort, performance, custom)
- Dynamic window mode for automatic cheapest-hour selection
- Legionella protection scheduling
- Away and bath mode support

## Installation

### Manual Installation

1. Copy the integration folder (e.g., `water_heater_scheduler/`) to your Home Assistant `custom_components/` directory:
   ```
   config/
   └── custom_components/
       └── water_heater_scheduler/
           ├── __init__.py
           ├── config_flow.py
           ├── const.py
           ├── coordinator.py
           ├── manifest.json
           ├── sensor.py
           └── strings.json
   ```

2. Restart Home Assistant

3. Go to **Settings → Devices & Services → Add Integration**

4. Search for "Water Heater Scheduler"

5. Follow the setup wizard

### HACS Installation (Coming Soon)

Once published to HACS, you can install directly from the HACS store.

## Configuration

The integration uses a multi-step configuration wizard:

### Step 1: Basic Setup
- **Water heater entity** - Select your water heater
- **Price sensor** - Select the sensor providing electricity prices
- **Temperature preset** - Choose eco, comfort, performance, or custom
- **Dynamic window mode** - Automatically find the cheapest heating window

### Step 2: Advanced Settings
- Away/bath mode helper entities
- Night window timing
- Legionella protection settings
- Cycle gap and evaluation interval

### Step 3: Custom Temperatures (if preset = custom)
- Override individual temperature targets

## Entities Created

The integration creates a device with these sensors:

| Entity | Description |
|--------|-------------|
| `sensor.{name}_current_program` | Active heating program (Idle, Night, Day, etc.) |
| `sensor.{name}_target_temperature` | Current target temperature |
| `sensor.{name}_status` | Human-readable status message |

## Migrating from the Add-on

If you're currently using the Water Heater Scheduler add-on:

1. Note your current settings from the add-on configuration
2. Stop the add-on
3. Install this integration
4. Configure with the same settings
5. Uninstall the add-on

The integration provides the same functionality with a better UI experience.
