## ADDED Requirements

### Requirement: Asset-Based Installation Model
The system SHALL model a Home Assistant installation as a collection of HEMS assets rather than raw standalone entity IDs.

#### Scenario: Create battery asset
- **WHEN** the user adds a battery asset in the HEMS web interface
- **THEN** the system stores a distinct asset record with type `battery`, user-defined name, operating mode, and mapped entities

#### Scenario: Multiple asset types can coexist
- **WHEN** the installation contains battery, solar, and grid assets
- **THEN** the system stores them as separate asset records
- **AND** each asset maintains its own mappings and validation state

### Requirement: Asset Workspace Structure
The system SHALL provide dedicated asset management views that separate overview, entity mapping, capabilities, constraints, and diagnostics.

#### Scenario: User opens an asset detail page
- **WHEN** the user selects an asset in the assets area
- **THEN** the system provides an asset overview, mapping controls, capability status, constraints, and diagnostics for that asset

#### Scenario: Asset list shows readiness at a glance
- **WHEN** the user views the asset list
- **THEN** the system shows asset type, name, operating mode, validation status, and warnings for each asset

### Requirement: Home Assistant Entity Discovery
The system SHALL discover Home Assistant entities and present them for mapping during setup.

#### Scenario: Discovery lists candidate entities
- **WHEN** the user opens the asset setup flow
- **THEN** the system queries Home Assistant for available entities
- **AND** presents candidate entities filtered by domain, device class, or asset-relevant metadata where available

#### Scenario: Discovery refreshes after new entities appear
- **WHEN** new compatible Home Assistant entities are added after HEMS was installed
- **THEN** the user can refresh discovery
- **AND** newly available candidates appear for mapping

### Requirement: Capability-Based Mapping Validation
The system SHALL validate mapped entities against the required and optional capabilities of the selected asset type.

#### Scenario: Battery asset meets required capabilities
- **WHEN** a battery asset has valid mappings for all required battery capabilities
- **THEN** the asset validation state is `ready`
- **AND** battery planning can use that asset

#### Scenario: Missing required capability blocks readiness
- **WHEN** a required capability such as battery SOC or battery mode control is not mapped
- **THEN** the asset validation state is `invalid`
- **AND** the system identifies the missing capability and affected entity mapping

#### Scenario: Optional capability is absent
- **WHEN** an optional capability such as solar forecast input is not mapped
- **THEN** the asset remains usable
- **AND** the system marks the capability as unavailable for planning and explainability

#### Scenario: Mapping screen distinguishes required and optional capabilities
- **WHEN** the user configures an asset mapping
- **THEN** the system labels each capability as required or optional
- **AND** the validation UI makes clear which missing mappings block readiness and which only reduce planning quality

### Requirement: Per-Asset Operating Modes
The system SHALL allow each asset to define its own operating mode independently of the global HEMS mode.

#### Scenario: Asset disabled
- **WHEN** the user sets an asset to `disabled`
- **THEN** the system excludes that asset from module planning
- **AND** the web interface shows the asset as intentionally inactive

#### Scenario: Asset remains in dry run under broader system enablement
- **WHEN** the global system is active and an asset mode is `dry_run`
- **THEN** the system may simulate actions for that asset
- **AND** no control action is executed for that asset

### Requirement: Mapping Diagnostics
The system SHALL provide diagnostics for asset mappings so users can understand why an asset is or is not usable.

#### Scenario: Mapping test succeeds
- **WHEN** the user runs a mapping validation check for an asset
- **THEN** the system verifies entity reachability, state readability, and required capability coverage
- **AND** returns a success result with the checked capabilities

#### Scenario: Mapping test fails on stale or missing data
- **WHEN** an entity is unavailable, stale, or returns unusable state data during validation
- **THEN** the system reports the failed check
- **AND** the diagnostic output includes the entity involved and the reason for failure

#### Scenario: Current entity value preview supports mapping confidence
- **WHEN** the user is selecting or validating a mapped entity
- **THEN** the system can show the current entity value or availability state where possible
- **AND** the preview helps the user confirm that the selected entity is the intended one
