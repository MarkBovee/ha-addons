## ADDED Requirements

### Requirement: Live grid charge trim
While a solar-aware charge window is active, the battery manager SHALL set the grid charge power to `floor((required_rate - solar_surplus + buffer) / step) * step`, clamped between 0 W and the planned window power, where `required_rate` is the remaining charge deficit divided by the remaining charge-window hours and `solar_surplus` is `max(0, solar_power - house_load)`.

#### Scenario: Solar surplus rises
- **WHEN** live solar surplus increases during an active solar-aware charge window
- **THEN** the published grid charge power SHALL decrease in steps of the configured step size, down to 0 W

#### Scenario: Solar surplus falls
- **WHEN** live solar surplus drops during an active solar-aware charge window
- **THEN** the published grid charge power SHALL increase again, never above the planned window power

### Requirement: Trim exclusions
The battery manager SHALL NOT trim negative-price charge windows, windows that are not solar-aware, or windows while solar, house-load or SOC readings are unavailable.

#### Scenario: Sensor unavailable
- **WHEN** the solar or house-load reading is unavailable
- **THEN** the planned window power SHALL remain published unchanged

### Requirement: Limited publish rate
The battery manager SHALL republish a trimmed schedule only when the trimmed power differs from the currently published power and at least `adaptive_power_grace_seconds` have passed since the previous trim.
