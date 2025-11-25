# Energy Usage Reporter Add-on

## Purpose

Rebuild the `UsageReport` app as a telemetry-focused add-on that records 15-minute intervals of power usage, solar production, and battery behavior, ties them back to the current battery schedule, and publishes Markdown reports.

## Key Behaviors

- Align interval collection to exact 00/15/30/45 minutes using the Home Assistant scheduler.
- Persist interval data in the add-on state directory and automatically prune beyond the configured retention window.
- Generate Markdown reports daily at midnight plus ad-hoc on demand, then update summary sensors inside Home Assistant.
- Tag each interval with whether the battery schedule was active and what type of activity (charge/discharge) occurred.

## User Settings

| Key | Type | Default | Description |
| --- | --- | --- | --- |
| `interval_minutes` | integer | `15` | Collection cadence. |
| `retention_days` | integer | `1` | Number of days to keep raw intervals. |
| `grid_power_sensor_id` | string | `sensor.average_power_usage_15` | Grid import/export data source. |
| `battery_power_sensor_id` | string | `sensor.battery_grid_power_15` | Battery charge/discharge sensor. |
| `solar_power_sensor_id` | string | `sensor.solar_production_15` | Solar production sensor. |
| `price_table_sensor_id` | string | `sensor.energy_price_table` | Optional sensor providing price curve (fallback to price helper). |
| `report_output_dir` | string | `/data/reports/daily` | Directory for Markdown reports (within HA add-on data). |
| `generate_markdown_reports` | boolean | `true` | Toggle for report generation. |
| `publish_summaries` | boolean | `true` | Whether to push HA sensors with summary stats. |
| `schedule_check_interval_minutes` | integer | `60` | How often to validate schedule alignment. |

## Home Assistant Entities

| Entity | Direction | Description |
| --- | --- | --- |
| `sensor.ca_interval_import_cost` | write | Current interval import cost. |
| `sensor.ca_interval_export_revenue` | write | Current interval export revenue. |
| `sensor.ca_interval_battery_variance` | write | Difference between scheduled and actual battery power. |
| `sensor.ca_usage_daily_summary` | write | JSON summary of yesterday's performance with key metrics. |
| `sensor.ca_usage_latest_report` | write | File path attribute referencing latest Markdown file. |
| `binary_sensor.ca_usage_reporter_active` | write | Whether data collection is running. |

## Diagnostics & Logging

- Structured logs for each interval capture (with warnings if sensors unavailable).
- Service `energy_usage_reporter.generate_now` to create an on-demand report.

## Future Extensions

- Publish data to external analytics (InfluxDB/Prometheus).
- Visualize profit/loss per schedule period.

## Related Documentation

- [Add-on Suite Plan](addon-suite-plan.md)
- [Battery Optimizer](battery-optimizer-addon.md) – Source of battery schedule data
- [Price Helper Service](price-helper-service-addon.md) – Dependency for electricity pricing
