## ADDED Requirements

### Requirement: Battery Module Registration
The system SHALL provide a battery module that participates in HEMS planning only when enabled and backed by a valid battery asset.

#### Scenario: Enabled battery module with valid asset
- **WHEN** the battery module is enabled and at least one battery asset is in a ready state
- **THEN** the module is included in the planning cycle
- **AND** it produces battery planning proposals for the decision engine

#### Scenario: Battery module blocked by invalid asset
- **WHEN** the battery module is enabled but no battery asset has valid required capabilities
- **THEN** the module does not produce actionable proposals
- **AND** the module status explains which battery requirements are missing

### Requirement: Battery Module Strategy Configuration
The system SHALL allow battery-specific strategy and protection settings to be configured through the HEMS web interface.

#### Scenario: User configures battery strategy
- **WHEN** the user updates battery module settings such as reserve behavior, solar-aware charging, negative-price handling, or planning aggressiveness
- **THEN** the battery module uses those settings in subsequent planning cycles
- **AND** the module settings persist across restarts

#### Scenario: User sees linked battery assets in module settings
- **WHEN** the user opens the battery module configuration
- **THEN** the interface shows which battery assets are available to the module
- **AND** the module status reflects whether those assets are ready, degraded, or blocked

### Requirement: Battery Normalized Inputs
The battery module SHALL consume battery-relevant inputs through the HEMS asset and capability model rather than hard-coded entity names.

#### Scenario: Module reads normalized battery state
- **WHEN** the planning cycle runs for a mapped battery asset
- **THEN** the battery module reads SOC, battery power, house load, grid power, and configured control capabilities through the normalized HEMS model

#### Scenario: Module uses optional price and solar inputs
- **WHEN** price curves or solar-related capabilities are available for the mapped installation
- **THEN** the battery module incorporates those inputs into its planning proposal
- **AND** the explanation identifies their influence on the plan

### Requirement: Battery Dry-Run Planning
The battery module SHALL produce dry-run charge or discharge proposals based on available prices, battery state, and configured battery policies.

#### Scenario: Low-price charging proposal
- **WHEN** the planning horizon contains eligible low-price intervals and the battery is below its configured maximum target
- **THEN** the battery module proposes one or more future charge actions
- **AND** each proposal identifies the expected interval, target behavior, and rationale

#### Scenario: High-price discharge proposal
- **WHEN** the planning horizon contains profitable discharge intervals and the battery is above its configured reserve target
- **THEN** the battery module proposes one or more discharge actions
- **AND** each proposal identifies the expected interval, target behavior, and rationale

#### Scenario: No action due to battery protection
- **WHEN** the battery is at or below a configured reserve or protection threshold
- **THEN** the battery module refrains from discharge proposals
- **AND** the explanation identifies the protection threshold that blocked action

### Requirement: Battery Proposal Explanations
The battery module SHALL provide structured reasons for each proposed, deferred, or blocked battery action.

#### Scenario: Proposed action includes battery reasoning
- **WHEN** the battery module proposes a charge action
- **THEN** the proposal includes the battery state, relevant price or solar context, and policy reasoning that support the action

#### Scenario: Blocked action includes battery reasoning
- **WHEN** the battery module skips or blocks a candidate action
- **THEN** the module output identifies the threshold, missing capability, or conflicting condition that caused the block

### Requirement: Battery Logic Reuse Boundary
The battery module SHALL allow reuse of existing battery-manager domain logic without inheriting the old add-on's fixed entity contracts.

#### Scenario: Existing battery logic adapted behind HEMS interfaces
- **WHEN** battery planning logic from the current repository is reused inside HEMS
- **THEN** the logic consumes normalized HEMS battery inputs and emits HEMS battery proposals
- **AND** the reused logic is not coupled directly to legacy battery-manager entity IDs
