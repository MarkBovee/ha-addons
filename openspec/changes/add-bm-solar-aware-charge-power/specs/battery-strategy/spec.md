## ADDED Requirements

### Requirement: Forecast-Assisted Charge Power Allocation
The system SHALL reduce commanded charge power during today's planned charge windows when a remaining-solar forecast indicates that part of the battery charge target can be satisfied by expected PV production.

#### Scenario: Remaining solar forecast reduces charge power
- **WHEN** the current schedule contains charge windows later today
- **AND** the battery SOC is below `soc.max_soc`
- **AND** `entities.remaining_solar_energy_entity` provides a valid remaining-energy value for today
- **THEN** the system SHALL recalculate the remaining charge deficit toward `soc.max_soc`
- **AND** the system SHALL reduce commanded charge power for today's remaining charge slots based on the usable remaining solar forecast
- **AND** the system SHALL keep every retained grid-charge slot at or above `solar_aware_charging.min_charge_power`

#### Scenario: Rolling hourly recalculation
- **WHEN** Battery Manager regenerates the schedule later in the same day
- **THEN** the system SHALL recompute charge power using the latest SOC, the latest remaining-solar value, and only the charge slots still remaining from the current time onward

#### Scenario: Forecast unavailable or invalid
- **WHEN** the remaining-solar entity is unavailable, invalid, or solar-aware charging is disabled
- **THEN** the system SHALL fall back to the existing ranked charge-slot power allocation without changing window selection

#### Scenario: Tomorrow slots are not discounted by today's forecast
- **WHEN** the schedule contains charge slots for tomorrow
- **THEN** the system SHALL apply the remaining-solar forecast only to today's remaining charge slots
- **AND** tomorrow charge slots SHALL keep the normal ranked charge-slot power allocation