# Mark Bovee's Home Assistant Addons

A collection of custom Home Assistant Supervisor addons.

## Repository Structure

This repository contains multiple Home Assistant addons, each in its own subdirectory:

```
ha-addons/
├── repository.json           # Repository metadata
├── README.md                 # This file
├── LICENSE                   # MIT License
├── run_addon.py              # Universal addon runner for local development
├── sync_shared.py            # Sync shared modules to all addons
├── shared/                   # Shared Python modules (source of truth)
│   ├── addon_base.py         # Logging, signal handling, main loop utilities
│   ├── ha_api.py             # Home Assistant REST API client
│   ├── config_loader.py      # Configuration loading utilities
│   └── mqtt_setup.py         # MQTT Discovery client setup
├── charge-amps-monitor/      # Charge Amps EV Charger Monitor addon
├── energy-prices/            # Nord Pool-based Energy Prices addon
└── [future-addons]/          # Additional addons will be added here
```

> **Note:** Each addon has its own copy of `shared/` for Docker builds. Always edit the root `shared/` folder and run `python sync_shared.py` to propagate changes.

## Installation

### Add Repository to Home Assistant

1. Go to **Settings** > **Add-ons** > **Add-on Store**
2. Click the three-dot menu (⋮) in the top right
3. Select **Repositories**
4. Add repository URL: `https://github.com/MarkBovee/ha-addons`
5. Click **Add**

### Install Addons

After adding the repository, all addons will appear in the Add-on Store. Install and configure each addon individually.

## Available Addons

### Charge Amps EV Charger Monitor

Monitor Charge Amps EV charger status and create Home Assistant entities.

**Features:**
- Automatic entity creation for charging status, power, consumption, and more
- Periodic updates (configurable interval)
- Secure authentication with Charge Amps API
- Comprehensive monitoring of charger status and metrics

**Installation:**
1. Add this repository (see above)
2. Find **Charge Amps - EV Charger Monitor** in the Add-on Store
3. Click **Install**
4. Configure your Charge Amps credentials
5. Click **Start**

For detailed documentation, see [charge-amps-monitor/README.md](charge-amps-monitor/README.md)

### Energy Prices

Fetch Nord Pool day-ahead electricity prices and calculate final import/export costs using customizable Jinja2 templates.

**Features:**
- 15-minute interval prices for the Dutch market (NL)
- Flexible Jinja2 templates for import/export price calculation
- Percentiles and price level classification (None/Low/Medium/High)
- 48-hour price curves exposed as Home Assistant sensor attributes

**Installation:**
1. Add this repository (see above)
2. Find **Energy Prices** in the Add-on Store
3. Click **Install**
4. Configure templates and options
5. Click **Start**

For detailed documentation, see [energy-prices/README.md](energy-prices/README.md)

## Development

### Local Testing

Use the universal addon runner for local development:

```bash
# List all available addons
python run_addon.py --list

# Run an addon (continuous mode)
python run_addon.py --addon energy-prices

# Run a single iteration then exit (for testing)
python run_addon.py --addon energy-prices --once

# Initialize .env from .env.example
python run_addon.py --addon energy-prices --init-env
```

The runner automatically syncs shared modules before execution.

### Shared Modules

Common utilities are in `shared/` at the repository root. Each addon needs its own copy for Docker builds:

```bash
# After editing shared/ modules, sync to all addons:
python sync_shared.py

# Or use run_addon.py which auto-syncs
python run_addon.py --addon <name>
```

See [agents.md](agents.md) for detailed development guidelines.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Support

For issues or questions, please open an issue on the [GitHub repository](https://github.com/MarkBovee/ha-addons).

