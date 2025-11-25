# Mark Bovee's Home Assistant Addons

A collection of custom Home Assistant Supervisor addons.

## Repository Structure

This repository contains multiple Home Assistant addons, each in its own subdirectory:

```
ha-addons/
├── repository.json           # Repository metadata
├── README.md                 # This file
├── LICENSE                   # MIT License
├── charge-amps-monitor/      # Charge Amps EV Charger Monitor addon
├── energy-prices/            # Nord Pool-based Energy Prices addon
└── [future-addons]/          # Additional addons will be added here
```

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

Each addon has its own development setup. See the individual addon directories for development instructions.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Support

For issues or questions, please open an issue on the [GitHub repository](https://github.com/MarkBovee/ha-addons).

