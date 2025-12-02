# Energy Prices Add-on Specification

## ADDED Requirements

### Requirement: Nord Pool Day-Ahead Price Fetching
The system SHALL fetch day-ahead electricity prices from the Nord Pool API for the Dutch market (NL) with 15-minute interval granularity.

#### Scenario: Successful price fetch for today
- **WHEN** the add-on requests today's prices from the Nord Pool API
- **THEN** the system returns 96 price intervals (15-minute increments)
- **AND** each interval contains deliveryStart, deliveryEnd (UTC timestamps), and price in EUR/MWh
- **AND** the HTTP response status is 200

#### Scenario: Tomorrow's prices not yet available
- **WHEN** the add-on requests tomorrow's prices before 13:00 CET
- **THEN** the Nord Pool API returns HTTP 204 (No Content)
- **AND** the system logs this as expected behavior
- **AND** the add-on continues operation without error

#### Scenario: Network failure during API fetch
- **WHEN** the Nord Pool API request times out or connection fails
- **THEN** the system logs the error with context
- **AND** skips this update cycle
- **AND** retries on the next scheduled fetch interval

### Requirement: Price Unit Conversion
The system SHALL convert Nord Pool prices from EUR/MWh to cents/kWh with proper precision.

#### Scenario: Convert EUR/MWh to cents/kWh
- **WHEN** the Nord Pool API returns a price of 97.94 EUR/MWh
- **THEN** the system converts it to 9.794 cents/kWh (multiply by 0.1)
- **AND** stores the value with at least 4 decimal precision

#### Scenario: Maintain timestamp integrity
- **WHEN** parsing price intervals from the API
- **THEN** all timestamps are stored as UTC-aware datetime objects
- **AND** deliveryStart and deliveryEnd are preserved exactly as provided
- **AND** no timezone conversion is applied during storage

### Requirement: Jinja2 Template Processing
The system SHALL apply user-defined Jinja2 templates to calculate final import and export prices from market prices.

#### Scenario: Valid template with VAT calculation
- **WHEN** the import template is `{{ (marktprijs * 1.21 + 2.48 + 12.28) | round(4) }}`
- **AND** the market price is 9.794 cents/kWh
- **THEN** the system calculates 26.6307 cents/kWh
- **AND** the result is rounded to exactly 4 decimal places

#### Scenario: Invalid template syntax at startup
- **WHEN** the import_price_template contains syntax error: `{{ marktprijs *`
- **THEN** the add-on fails to start
- **AND** logs a clear error message with the line number and syntax issue
- **AND** exits with non-zero status code

#### Scenario: Template rendering error during calculation
- **WHEN** a template attempts to divide by zero or produces non-numeric output
- **THEN** the system logs the error with template content and input value
- **AND** skips that specific price interval
- **AND** continues processing remaining intervals

#### Scenario: Export price template without fees
- **WHEN** the export template is `{{ marktprijs | round(4) }}`
- **AND** the market price is 9.794 cents/kWh
- **THEN** the system calculates 9.7940 cents/kWh (no additional fees)

### Requirement: Template Variable Exposure
The system SHALL expose the `marktprijs` variable in Jinja2 template context representing the market price in cents/kWh.

#### Scenario: Template accesses marktprijs variable
- **WHEN** a template uses `{{ marktprijs }}`
- **THEN** the variable contains the Nord Pool price converted to cents/kWh
- **AND** the value is a float with at least 4 decimal places
- **AND** no other variables are exposed in the template context

### Requirement: Template Security Sandboxing
The system SHALL use Jinja2 sandboxed environment to prevent code injection attacks.

#### Scenario: Template cannot access Python builtins
- **WHEN** a template attempts `{{ __import__('os').system('ls') }}`
- **THEN** the sandbox blocks access to __import__
- **AND** the template rendering fails with SecurityError
- **AND** the error is logged

### Requirement: Home Assistant Entity Management
The system SHALL create and update three Home Assistant entities with price data and derived metrics.

#### Scenario: Create import price sensor
- **WHEN** the add-on starts for the first time
- **THEN** the system creates entity `sensor.ep_price_import`
- **AND** the state contains the current import price in cents/kWh
- **AND** attributes include unit_of_measurement="cents/kWh"
- **AND** attributes include price_curve with 48 hours of forecast data

#### Scenario: Create export price sensor
- **WHEN** the add-on starts for the first time
- **THEN** the system creates entity `sensor.ep_price_export`
- **AND** the state contains the current export price in cents/kWh
- **AND** attributes include price_curve with 48 hours of forecast data

#### Scenario: Create price level classification sensor
- **WHEN** the add-on starts for the first time
- **THEN** the system creates entity `sensor.ep_price_level`
- **AND** the state is one of: None, Low, Medium, High
- **AND** attributes include p20, p40, p60 percentile values
- **AND** attributes include current_price for reference

#### Scenario: Update entity when prices change
- **WHEN** new prices are fetched from Nord Pool API
- **THEN** all three entities are updated via HA Supervisor API
- **AND** the state reflects current interval price or level
- **AND** attributes are refreshed with latest data
- **AND** last_update timestamp is set to current UTC time

#### Scenario: Entity update fails due to HA unavailable
- **WHEN** the HA Supervisor API returns error or times out
- **THEN** the system logs the error
- **AND** continues operation (price fetching and calculation)
- **AND** retries entity update on next cycle

### Requirement: Price Curve Attribute Format
The system SHALL expose 48-hour price forecasts in entity attributes as structured JSON arrays.

#### Scenario: Price curve contains 48 hours of data
- **WHEN** today's and tomorrow's prices are both available
- **THEN** the price_curve attribute contains up to 192 intervals (96 today + 96 tomorrow)
- **AND** each interval includes: start (ISO 8601 UTC), end (ISO 8601 UTC), price (float)
- **AND** intervals are sorted chronologically

#### Scenario: Price curve handles missing tomorrow's data
- **WHEN** tomorrow's prices are not yet available (HTTP 204)
- **THEN** the price_curve contains only today's 96 intervals
- **AND** the attribute indicates partial data availability
- **AND** no placeholder or null values are included

### Requirement: Percentile Calculation
The system SHALL compute price distribution percentiles (P05, P20, P40, P60, P80, P95) from import prices.

#### Scenario: Calculate percentiles from full dataset
- **WHEN** import prices are calculated for all 192 intervals
- **THEN** the system sorts prices in ascending order
- **AND** calculates P05, P20, P40, P60, P80, P95 using linear interpolation
- **AND** stores percentiles in sensor.ep_price_import attributes

#### Scenario: Calculate percentiles with partial data
- **WHEN** only 96 intervals are available (tomorrow not published)
- **THEN** percentiles are calculated from available data only
- **AND** the calculation proceeds without error

### Requirement: Price Level Classification
The system SHALL classify current price into None/Low/Medium/High based on percentile thresholds.

#### Scenario: Price below P20 classified as None
- **WHEN** current import price is 18.00 cents/kWh
- **AND** P20 is 22.12 cents/kWh
- **THEN** sensor.ep_price_level state is "None"
- **AND** attributes show P20, P40, P60 values

#### Scenario: Price between P20 and P40 classified as Low
- **WHEN** current import price is 25.00 cents/kWh
- **AND** P20 is 22.12 cents/kWh
- **AND** P40 is 28.46 cents/kWh
- **THEN** sensor.ep_price_level state is "Low"

#### Scenario: Price between P40 and P60 classified as Medium
- **WHEN** current import price is 32.00 cents/kWh
- **AND** P40 is 28.46 cents/kWh
- **AND** P60 is 35.68 cents/kWh
- **THEN** sensor.ep_price_level state is "Medium"

#### Scenario: Price above P60 classified as High
- **WHEN** current import price is 40.00 cents/kWh
- **AND** P60 is 35.68 cents/kWh
- **THEN** sensor.ep_price_level state is "High"

### Requirement: Configurable Update Interval
The system SHALL fetch and update prices at user-configured intervals with default of 60 minutes.

#### Scenario: Fetch at default interval
- **WHEN** fetch_interval_minutes is not configured
- **THEN** the system fetches prices every 60 minutes
- **AND** sleeps between fetches checking shutdown flag every second

#### Scenario: Fetch at custom interval
- **WHEN** fetch_interval_minutes is set to 30
- **THEN** the system fetches prices every 30 minutes
- **AND** maintains responsive shutdown during sleep

#### Scenario: Minimum interval validation
- **WHEN** fetch_interval_minutes is set to less than 1
- **THEN** the add-on fails to start
- **AND** logs a validation error

### Requirement: Graceful Shutdown
The system SHALL handle SIGTERM and SIGINT signals gracefully without data loss or corruption.

#### Scenario: Shutdown during normal operation
- **WHEN** SIGTERM signal is received
- **THEN** the shutdown_flag is set
- **AND** the main loop exits cleanly after current operation
- **AND** logs shutdown message
- **AND** process exits with code 0

#### Scenario: Shutdown during sleep interval
- **WHEN** SIGINT (Ctrl+C) is received during sleep
- **THEN** the sleep is interrupted immediately
- **AND** the main loop checks shutdown_flag and exits
- **AND** process exits with code 0 within 2 seconds

### Requirement: Configuration Schema Validation
The system SHALL validate all configuration options at startup using Home Assistant schema.

#### Scenario: Valid configuration accepted
- **WHEN** config.yaml specifies delivery_area="NL", currency="EUR", timezone="CET"
- **AND** import_price_template and export_price_template are valid strings
- **AND** fetch_interval_minutes=60
- **THEN** the add-on starts successfully
- **AND** logs configuration summary

#### Scenario: Missing required template fails validation
- **WHEN** import_price_template is empty or missing
- **THEN** Home Assistant supervisor prevents add-on start
- **AND** displays schema validation error in UI

#### Scenario: Invalid interval value fails validation
- **WHEN** fetch_interval_minutes is set to "abc" (non-integer)
- **THEN** Home Assistant supervisor prevents add-on start
- **AND** displays type validation error

### Requirement: Structured Logging
The system SHALL log all operations with appropriate severity levels and contextual information.

#### Scenario: Log API request parameters
- **WHEN** fetching prices from Nord Pool API
- **THEN** logs include date, delivery_area, currency at INFO level
- **AND** response status and interval count are logged

#### Scenario: Log template calculation errors
- **WHEN** template rendering fails for an interval
- **THEN** logs include ERROR level message
- **AND** context includes template content, input value, error message
- **AND** stack trace is included for unexpected errors

#### Scenario: Log entity updates
- **WHEN** updating Home Assistant entities
- **THEN** logs include INFO level message
- **AND** entity IDs and new state values are logged
- **AND** update failures are logged at ERROR level

### Requirement: Default Template Examples
The system SHALL provide working example templates in documentation for Dutch energy market.

#### Scenario: Dutch import template example
- **WHEN** user views documentation
- **THEN** example includes VAT (21%), grid fee (2.48 cents), energy tax (12.28 cents)
- **AND** template syntax is: `{{ (marktprijs * 1.21 + 2.48 + 12.28) | round(4) }}`
- **AND** example explains each component

#### Scenario: Dutch export template example
- **WHEN** user views documentation
- **THEN** example shows simple pass-through: `{{ marktprijs | round(4) }}`
- **AND** explains that export typically has no additional fees

## Acceptance Criteria

- [ ] Nord Pool API integration fetches 96 intervals per day successfully
- [ ] Price conversion EUR/MWh → cents/kWh is accurate (multiply by 0.1)
- [ ] Template validation catches syntax errors at startup (fail-fast)
- [ ] Import and export prices calculated with 4-decimal precision
- [ ] Percentiles (P05, P20, P40, P60, P80, P95) computed correctly
- [ ] Price level classification (None/Low/Medium/High) works based on P20/P40/P60
- [ ] Three HA entities created: sensor.ep_price_import, sensor.ep_price_export, sensor.ep_price_level
- [ ] Price curves contain up to 48 hours of UTC-timestamped data
- [ ] Entity attributes include percentiles, price curves, metadata
- [ ] Graceful shutdown responds to SIGTERM/SIGINT within 2 seconds
- [ ] Configuration schema validates all options correctly
- [ ] Logs provide clear information for debugging and monitoring
- [ ] Documentation includes working Dutch template examples
- [ ] Add-on runs stably for 24+ hours without memory leaks or errors
