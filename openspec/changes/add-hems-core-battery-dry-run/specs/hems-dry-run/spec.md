## ADDED Requirements

### Requirement: Dry-Run-Only First Release Behavior
The system SHALL support a dry-run mode that evaluates and explains actions without issuing device control commands.

#### Scenario: Dry run simulates but does not execute
- **WHEN** the HEMS is operating in `dry_run`
- **THEN** the system computes proposed and final actions for the planning horizon
- **AND** no Home Assistant service call, MQTT command, or direct control write is sent for those actions

#### Scenario: Dry run status is visible
- **WHEN** the HEMS is in `dry_run`
- **THEN** the current mode is visible in the web interface and diagnostic outputs
- **AND** users can distinguish simulated actions from future executable behavior

### Requirement: Decision Timeline Preview
The system SHALL provide a timeline preview of the decisions it would take over the configured planning horizon.

#### Scenario: User opens dry-run timeline
- **WHEN** a planning cycle has completed
- **THEN** the system shows scheduled or proposed actions over upcoming intervals
- **AND** each timeline entry identifies the asset, module, action type, and expected time window

#### Scenario: Timeline includes selected and blocked outcomes
- **WHEN** the user inspects the planning timeline in detail
- **THEN** the system can show which candidate actions were selected, blocked, deferred, or superseded
- **AND** each outcome retains its decision status

### Requirement: Explainability Per Decision
The system SHALL expose the reasons behind each simulated decision and blocked action.

#### Scenario: User inspects a proposed action
- **WHEN** the user opens a dry-run action detail
- **THEN** the system shows the inputs, rules, constraints, and policy reasons that produced the action

#### Scenario: User inspects a blocked action
- **WHEN** the system does not include a candidate action in the final plan
- **THEN** the decision details show whether it was blocked, deferred, or superseded
- **AND** the blocking reason is identified

#### Scenario: Explain view answers why and why not
- **WHEN** the user asks why an action was taken or why an asset remained idle
- **THEN** the system shows the relevant inputs, thresholds, constraints, and winning decision path
- **AND** the output distinguishes between positive reasons and blocking reasons

### Requirement: Data Quality Visibility
The system SHALL expose data quality issues that affect dry-run confidence.

#### Scenario: Input data is stale
- **WHEN** a required entity has stale data during planning
- **THEN** the dry-run output marks the affected decision or asset as degraded
- **AND** the explanation identifies the stale input

#### Scenario: Input data is incomplete
- **WHEN** optional or required inputs are missing
- **THEN** the dry-run output indicates which assumptions or fallbacks were used
- **AND** users can see the impact on the simulated plan

### Requirement: Decision History Retention
The system SHALL retain recent dry-run decisions so users can inspect prior planning outcomes.

#### Scenario: Recent decision history available
- **WHEN** multiple planning cycles have run
- **THEN** the system stores recent dry-run plan results in persisted state
- **AND** the user can inspect earlier decisions and their timestamps

#### Scenario: History view shows planning evolution
- **WHEN** the user opens decision history in the web interface
- **THEN** the system shows previous plans, their timestamps, and summary outcomes
- **AND** the user can drill into a past decision for more detail
