# Delta: Battery Strategy Specification

## ADDED Requirements

### Requirement: Summer Mode Detection
The system SHALL detect summer mode when the majority of the configured top-N cheapest price periods for today fall within a configured noon window.

#### Scenario: Midday majority enables summer mode
- **WHEN** top-N cheapest periods are calculated from today's import price curve
- **AND** more than half of those periods start between the configured `summer_mode_noon_start_hour` and `summer_mode_noon_end_hour`
- **THEN** summer mode is marked active for the generated schedule

#### Scenario: Non-midday majority disables summer mode
- **WHEN** top-N cheapest periods are calculated
- **AND** half or fewer periods fall inside the configured noon window
- **THEN** summer mode is marked inactive

#### Scenario: Missing or invalid curve disables summer mode safely
- **WHEN** the import price curve is missing, empty, or contains insufficient valid timestamps
- **THEN** summer mode defaults to inactive
- **AND** schedule generation continues without failure

### Requirement: Summer Mode Configuration
The system SHALL provide configuration options to control summer-mode detection.

#### Scenario: Summer mode enabled with defaults
- **WHEN** no explicit summer-mode options are set
- **THEN** detection is enabled by default
- **AND** noon window defaults to 10:00-16:00
- **AND** top-N defaults to 3

#### Scenario: Summer mode explicitly disabled
- **WHEN** `heuristics.summer_mode_enabled` is set to false
- **THEN** summer mode remains inactive regardless of price curve shape

### Requirement: Summer Mode Visibility
The system SHALL surface summer-mode state in existing Battery Manager status outputs.

#### Scenario: Summer mode active in status context
- **WHEN** summer mode is active for the current schedule
- **THEN** published mode/reasoning/status output includes an explicit summer indicator

#### Scenario: Summer mode inactive in status context
- **WHEN** summer mode is inactive
- **THEN** published output indicates normal (non-summer) context

### Requirement: Summer Day-Start Schedule Indicator
The system SHALL publish a summer day-start indicator when a new daily schedule is generated while summer mode is active.

#### Scenario: Show summer icon on new summer day schedule
- **WHEN** a schedule is generated for a new day
- **AND** summer mode is active
- **THEN** schedule output includes `🌞 Nieuw dagschema (Summer)`
- **AND** the indicator is emitted at most once for that local day

#### Scenario: No summer icon when inactive
- **WHEN** a schedule is generated for a new day
- **AND** summer mode is inactive
- **THEN** schedule output does not include the summer day-start indicator

### Requirement: Summer Mode Non-Invasive Operation
The system SHALL keep summer mode informational in this change and SHALL NOT alter charge/discharge selection behavior.

#### Scenario: Strategy remains unchanged
- **WHEN** summer mode toggles active or inactive
- **THEN** existing load/discharge/adaptive/passive window selection logic remains unchanged
- **AND** schedule power assignment logic remains unchanged
