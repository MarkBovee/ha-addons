# Energy Prices Add-on

Fetch Nord Pool day-ahead electricity prices and calculate final import/export costs using simple price component fields.

## Overview

This add-on connects to the Nord Pool Day-Ahead Prices API to fetch 15-minute interval electricity prices for the Dutch market (NL) and automatically creates Home Assistant entities with:
- Current import price (with VAT, grid fees, and energy taxes)
- Current export price (feed-in tariff)
- Price level classification (None/Low/Medium/High)
- 48-hour price forecast with percentiles (P20/P40/P60)

## Features

- **Simple Price Calculation**: Configure VAT, markup, and energy tax separately - no templates required
- **15-Minute Granularity**: Fetch prices with 15-minute intervals (96 per day)
- **Price Classification**: Automatic classification of current price as None/Low/Medium/High based on percentiles
- **48-Hour Forecast**: Price curves with both today's and tomorrow's prices
- **Automatic Entity Creation**: Creates and updates Home Assistant sensors automatically
- **UTC Timestamps**: All timestamps stored in UTC to avoid DST confusion

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
   - Click **Energy Prices**
   - Click **Install**
   - Configure settings (see Configuration below)
   - Click **Start**

## Configuration

Configure the addon through the Home Assistant UI:

1. Go to **Settings** > **Add-ons** > **Energy Prices**
2. Click **Configuration**
3. Enter your settings:

### Configuration Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `delivery_area` | string | `NL` | Nord Pool delivery area (NL for Netherlands) |
| `currency` | string | `EUR` | Currency for price data |
| `timezone` | string | `CET` | Timezone for display (data stored in UTC) |
| `import_vat_multiplier` | float | `1.21` | VAT multiplier for import (1.21 = 21% VAT) |
| `import_markup` | float | `2.48` | Fixed markup in cents/kWh (€0.0248) |
| `import_energy_tax` | float | `12.28` | Energy tax in cents/kWh (€0.1228) |
| `export_vat_multiplier` | float | `1.21` | VAT multiplier for export (same as import for salderingsregeling) |
| `export_markup` | float | `2.48` | Fixed markup in cents/kWh for export |
| `export_energy_tax` | float | `12.28` | Energy tax in cents/kWh for export |
| `fetch_interval_minutes` | integer | `60` | How often to fetch new prices (1-1440 minutes) |

### Price Calculation Formula

The final price is calculated using a simple formula for both import and export:

```
final_price = (market_price × vat_multiplier) + markup + energy_tax
```

### Dutch Defaults

The defaults are configured for a typical Dutch energy contract with salderingsregeling:

| Component | Value | EUR/kWh | Description |
|-----------|-------|---------|-------------|
| VAT Multiplier | 1.21 | - | 21% BTW |
| Markup | 2.48 | €0.0248 | Supplier margin + grid costs |
| Energy Tax | 12.28 | €0.1228 | Energiebelasting |

**Example**: If market price is 10 cents/kWh:
```
(10 × 1.21) + 2.48 + 12.28 = 26.86 cents/kWh
```

### Export Settings (Salderingsregeling)

By default, export uses the **same values** as import for Dutch salderingsregeling (net metering).

If you want export to use only the market price (no fees), set:
- `export_vat_multiplier`: 1.0
- `export_markup`: 0.0
- `export_energy_tax`: 0.0

## Created Entities

The addon creates the following Home Assistant entities:

### `sensor.ep_price_import`
Current electricity import price in cents/kWh.

**Attributes:**
- `unit_of_measurement`: "cents/kWh"
- `device_class`: "monetary"
- `price_curve`: Array of 48 hours of prices with UTC timestamps
- `percentiles`: P05, P20, P40, P60, P80, P95 values
- `last_update`: When prices were last fetched

### `sensor.ep_price_export`
Current electricity export price (feed-in tariff) in cents/kWh.

**Attributes:**
- `unit_of_measurement`: "cents/kWh"
- `device_class`: "monetary"
- `price_curve`: Array of 48 hours of prices with UTC timestamps
- `last_update`: When prices were last fetched

### `sensor.ep_price_level`
Current price level classification: "None", "Low", "Medium", or "High".

**Attributes:**
- `current_price`: Current import price
- `p20`: 20th percentile threshold (None/Low boundary)
- `p40`: 40th percentile threshold (Low/Medium boundary)
- `p60`: 60th percentile threshold (Medium/High boundary)
- `classification_rules`: Explanation of level determination

**Level Classification:**
- **None**: Current price < P20 (bottom 20%, cheapest times)
- **Low**: P20 ≤ Current price < P40 (below average)
- **Medium**: P40 ≤ Current price < P60 (average)
- **High**: Current price ≥ P60 (top 40%, most expensive)

## Usage Examples

### Example 1: Automation Based on Price Level
```yaml
automation:
  - alias: "Start washing machine when price is low"
    trigger:
      - platform: state
        entity_id: sensor.ep_price_level
        to: "None"
    action:
      - service: switch.turn_on
        target:
          entity_id: switch.washing_machine
```

### Example 2: Dashboard with Price Graph
```yaml
type: custom:apexcharts-card
header:
  show: true
  title: "Electricity Prices (48h)"
series:
  - entity: sensor.ep_price_import
    data_generator: |
      return entity.attributes.price_curve.map((point) => {
        return [new Date(point.start).getTime(), point.price];
      });
```

## Troubleshooting

### Template Validation Errors
**Problem:** Add-on fails to start with "Template syntax error"

**Solution:**
1. Check your template syntax in the configuration
2. Ensure all `{%` blocks are properly closed with `%}`
3. Test template with simple version: `{{ marktprijs }}`
4. Check add-on logs for detailed error message with line number

### No Prices Available
**Problem:** Entities show "unavailable" or "unknown"

**Solution:**
1. Check if tomorrow's prices are published (typically after 13:00 CET)
2. Verify Nord Pool API is accessible
3. Check add-on logs for API errors
4. Ensure `delivery_area` is set correctly (NL for Netherlands)

### Price Seems Wrong
**Problem:** Calculated price doesn't match expected value

**Solution:**
1. Verify template formula matches your energy contract
2. Check if `marktprijs` is in cents/kWh (not EUR/MWh)
3. Verify VAT percentage and fees in template
4. Compare with Nord Pool website: https://data.nordpoolgroup.com/

## Local Development

For local testing without Home Assistant:

1. Copy `.env.example` to `.env`:
   ```bash
   cp .env.example .env
   ```

2. Edit `.env` with your settings:
   ```env
   DELIVERY_AREA=NL
   CURRENCY=EUR
   TIMEZONE=CET
   
   # Import price components
   IMPORT_VAT_MULTIPLIER=1.21
   IMPORT_MARKUP=2.48
   IMPORT_ENERGY_TAX=12.28
   
   # Export price components  
   EXPORT_VAT_MULTIPLIER=1.0
   EXPORT_MARKUP=0.0
   EXPORT_ENERGY_TAX=0.0
   
   FETCH_INTERVAL_MINUTES=60
   HA_API_URL=http://localhost:8123
   HA_API_TOKEN=your_token_here
   ```

3. Run locally using the universal runner (from repo root):
   ```bash
   python run_addon.py --addon energy-prices
   ```

## Technical Details

### API Details
- **Endpoint**: `https://dataportal-api.nordpoolgroup.com/api/DayAheadPrices`
- **Data**: 15-minute intervals (96 per day)
- **Format**: Prices in EUR/MWh, converted to cents/kWh (×0.1)
- **Availability**: Tomorrow's prices published around 13:00 CET

### Data Processing
1. Fetch today's and tomorrow's prices from Nord Pool API
2. Convert EUR/MWh to cents/kWh
3. Apply import/export templates to each 15-minute interval
4. Calculate percentiles (P05, P20, P40, P60, P80, P95)
5. Determine current price level based on percentiles
6. Update Home Assistant entities with state and attributes

### Performance
- Memory usage: ~50MB
- CPU usage: <5% on Raspberry Pi 4
- Network: ~40KB per fetch cycle
- Update frequency: Configurable (default: 60 minutes)

## Support

For issues or questions, please open an issue on the [GitHub repository](https://github.com/MarkBovee/ha-addons).

## License

This project is licensed under the MIT License.
