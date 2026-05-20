## ADDED Requirements

### Requirement: Module Proposal Aggregation
The system SHALL collect planning proposals from each enabled HEMS module before producing a final plan.

#### Scenario: One enabled module contributes proposals
- **WHEN** only the battery module is enabled and has a valid asset
- **THEN** the decision engine receives battery planning proposals from that module
- **AND** the final plan is derived from those proposals

#### Scenario: Disabled modules do not contribute
- **WHEN** a module is disabled
- **THEN** the decision engine excludes it from the planning cycle
- **AND** no proposals are requested from that module

### Requirement: Central Final Plan Resolution
The system SHALL generate one final HEMS plan for the home after evaluating all module proposals, global policies, and active constraints.

#### Scenario: Final plan built from valid proposals
- **WHEN** one or more enabled modules submit valid proposals
- **THEN** the decision engine produces a final plan for the current planning horizon
- **AND** the plan contains selected actions, skipped actions, and reasons

#### Scenario: No valid proposals available
- **WHEN** no enabled module can produce a valid proposal
- **THEN** the decision engine produces an empty or blocked plan
- **AND** the result includes the reasons planning could not proceed

### Requirement: Global Policy Configuration
The system SHALL expose configurable global planning policies that influence how the decision engine resolves the final plan.

#### Scenario: User selects a global strategy profile
- **WHEN** the user chooses a strategy such as cost saver, self-consumption, balanced, comfort first, or battery backup in the web interface
- **THEN** the decision engine applies that policy set during plan resolution
- **AND** the active policy is reflected in planning explanations

#### Scenario: User configures fallback behavior
- **WHEN** the user defines behavior for missing or degraded data
- **THEN** the decision engine applies those fallback rules when required inputs are unavailable
- **AND** the resulting plan records the fallback path that was taken

### Requirement: Proposal Conflict Handling
The system SHALL resolve conflicts between module proposals using explicit priorities and constraints.

#### Scenario: Hard constraint blocks a proposed action
- **WHEN** a module proposes an action that violates a hard system or asset constraint
- **THEN** the decision engine rejects that action
- **AND** the final plan records the blocking constraint

#### Scenario: Competing proposals require prioritization
- **WHEN** two or more module proposals compete for limited energy or scheduling capacity
- **THEN** the decision engine applies configured priorities and policies
- **AND** the final plan records which proposal was selected and which was deferred or rejected

### Requirement: Planning Horizon Visibility
The system SHALL produce a plan for a defined planning horizon and expose the horizon used in the resulting decision output.

#### Scenario: Current and future horizon displayed
- **WHEN** a planning cycle completes in dry run
- **THEN** the system exposes decisions for the current time and upcoming intervals
- **AND** the output identifies the horizon covered by the plan

#### Scenario: User adjusts planning horizon
- **WHEN** the user updates the planning horizon in HEMS settings
- **THEN** the decision engine uses the new horizon for future planning cycles
- **AND** planning views reflect the updated horizon length

### Requirement: Explanation-Aware Decisions
The system SHALL retain structured reasoning for final decisions so the UI and diagnostics can explain why each action was selected, rejected, or blocked.

#### Scenario: Final action includes explanation
- **WHEN** the decision engine selects a battery charge action in dry run
- **THEN** the final plan includes the supporting price, state, policy, and module reasons for that action

#### Scenario: Rejected action includes explanation
- **WHEN** the decision engine rejects a module proposal
- **THEN** the final plan includes the reason for rejection or deferral
- **AND** the module and constraint involved are identified
