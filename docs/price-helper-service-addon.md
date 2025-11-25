# Price Helper Service Add-on

## Purpose

Provide a single add-on/service responsible for fetching, caching, and normalizing electricity prices (buy and sell) along with derived metrics like percentile thresholds (P20/P40/P60). All other add-ons depend on this data to stay consistent.

## Key Behaviors

- Pull Nord Pool/Dutch market day-ahead prices plus intraday updates; fall back to user-provided sensors when API failures occur.
- Apply VAT, grid fees, and markup/markdown per user configuration to expose separate buy and sell prices.
- Compute percentile thresholds, price bands, rolling averages, and classification (None/Low/Medium/High) that downstream add-ons can consume.
- Expose data via Home Assistant sensors, plus HTTP endpoints/services for bulk price curves.

## User Settings

| Key | Type | Default | Description |
| --- | --- | --- | --- |
| `market_api.endpoint` | url | `https://api.nordpoolgroup.com/v1/prices` | Day-ahead pricing endpoint. |
| `market_api.region` | string | `NL` | Market/area code. |
| `market_api.api_key` | string | – | Optional API key if provider requires authentication. |
| `fallback_sensor_id` | string | – | Sensor to read when API fails. |
| `region` | string | `NL` | Ensures 15-minute alignment. |
| `vat_percent` | number | `0.21` | VAT applied to buy price. |
| `grid_fee_eur_per_kwh` | number | `0.02` | Added to buy price. |
| `export_tariff_eur_per_kwh` | number | `0.00` | Added to sell price. |
| `buy_margin_percent` | number | `0` | Additional markup for buy pricing. |
| `sell_margin_percent` | number | `0` | Markdown for sell pricing. |
| `percentile_thresholds` | object | `{"p20":0.2,"p40":0.4,"p60":0.6}` | Defines the percentiles used for price levels. |
| `classification_levels` | object | `{"none":0.05,"low":0.15,"medium":0.25,"high":0.35}` | Map percentiles to Level enums. |
| `cache_duration_minutes` | integer | `60` | How long to cache price data. |
| `publish_buy_sell_sensors` | boolean | `true` | Whether to create dedicated buy/sell sensors. |

## Home Assistant Entities

| Entity | Direction | Description |
| --- | --- | --- |
| `sensor.energy_price_level` | write | Level enum derived from percentile thresholds. |
| `sensor.energy_price_percentiles` | write | Attributes for P05, P20, P40, P60, P80 etc. |
| `sensor.energy_price_curve` | write | JSON attribute containing the next 48 hours of prices. |
| `binary_sensor.energy_price_fetch_status` | write | Indicates whether the last fetch succeeded. |
| Services (`price_helper.get_curve`, `price_helper.notify_if_threshold_crossed`) | exposed | Allow other automations to pull data or register notifications. |

## Diagnostics & Logging

- Log fetch latency, cache hits/misses, and API error summaries.
- Metrics for threshold-crossing events (count per day).

## Related Documentation

- [Add-on Suite Plan](addon-suite-plan.md)

## Dependent Add-ons

This service is a dependency for:
- [Battery Optimizer](battery-optimizer-addon.md) – Uses price data for AI scheduling
- [Appliance Guard](appliance-guard-addon.md) – Uses price levels for curtailment decisions
- [Water Heater Scheduler](water-heater-scheduler-addon.md) – Uses price curves for optimal heating windows
- [Energy Usage Reporter](energy-usage-reporter-addon.md) – Uses price data for cost/revenue calculations
