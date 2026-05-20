## ADDED Requirements

### Requirement: Universal HEMS Add-on Runtime
The system SHALL provide a dedicated Home Assistant add-on named HEMS that runs independently from the repository's existing production add-ons.

#### Scenario: HEMS add-on starts independently
- **WHEN** the user installs and starts the HEMS add-on
- **THEN** the system starts its own runtime, configuration loading, and service lifecycle
- **AND** no existing add-on is required to be modified or replaced

#### Scenario: HEMS runs with persistent state
- **WHEN** the HEMS add-on restarts
- **THEN** the system restores persisted configuration and runtime state from `/data`
- **AND** previously configured assets and global modes remain available

### Requirement: Global Operating Modes
The system SHALL expose global operating modes that control whether the HEMS only observes, simulates, advises, or executes actions.

#### Scenario: Default mode is dry run
- **WHEN** the HEMS add-on is configured for the first time
- **THEN** the global operating mode is `dry_run`
- **AND** no real control actions are sent to Home Assistant entities

#### Scenario: Global pause disables active planning
- **WHEN** the user enables a global pause control
- **THEN** the system stops producing executable plans
- **AND** the current status indicates that planning is paused by the user

### Requirement: Web Management Interface
The system SHALL provide a web interface that acts as the primary functional configuration and operations surface for HEMS.

#### Scenario: User opens HEMS web interface
- **WHEN** the add-on web interface is opened
- **THEN** the system shows current connection status, configured assets, enabled modules, and operating mode

#### Scenario: User can manage modules in the web interface
- **WHEN** the user navigates to module management
- **THEN** the system shows all available modules with enable or disable controls
- **AND** disabled modules are excluded from planning

#### Scenario: Functional settings live in the web interface
- **WHEN** the user needs to configure assets, modules, policies, planning behavior, or diagnostics-related settings
- **THEN** the system provides those controls in the HEMS web interface
- **AND** Home Assistant add-on options are not required for normal HEMS operation

### Requirement: Web Navigation Structure
The system SHALL organize the web interface into dedicated operational areas for setup, control, and explainability.

#### Scenario: Main navigation exposes key product areas
- **WHEN** the user opens the main application shell
- **THEN** the system provides navigation for dashboard, assets, modules, planning, history, diagnostics, and settings

#### Scenario: Persistent top-level system state is visible
- **WHEN** the user navigates within the web interface
- **THEN** the system keeps current operating mode, system health, warning count, and global pause access visible without requiring page changes

### Requirement: Guided Onboarding Workflow
The system SHALL provide a first-run onboarding flow that guides the user from connectivity through initial dry-run planning.

#### Scenario: First-run setup wizard
- **WHEN** the HEMS has no configured assets on first launch
- **THEN** the system opens or prompts a guided onboarding flow
- **AND** the flow covers Home Assistant connectivity, entity discovery, asset selection, mapping validation, first module enablement, and dry-run start

#### Scenario: Incomplete setup remains visible after onboarding
- **WHEN** the user exits onboarding with missing required configuration
- **THEN** the system marks the installation as incomplete
- **AND** the web interface shows what remains to make the first plan possible

### Requirement: Layered Configuration Complexity
The system SHALL present simple defaults first and keep advanced controls accessible without overwhelming normal setup.

#### Scenario: Basic configuration shown first
- **WHEN** the user opens a configuration screen for an asset, module, or policy
- **THEN** the system shows the required and commonly used settings before advanced tuning controls

#### Scenario: Advanced options remain available
- **WHEN** the user needs deeper control of optimization or safety behavior
- **THEN** the system provides advanced settings sections without requiring direct file editing or hidden backend configuration

### Requirement: Persisted Configuration Management
The system SHALL persist HEMS configuration, module configuration, and asset mappings so they survive restarts.

#### Scenario: Save configuration changes
- **WHEN** the user updates an asset mapping or module setting in the web interface
- **THEN** the system persists the change to local add-on storage
- **AND** the updated configuration is used on the next planning cycle

#### Scenario: Invalid configuration is rejected
- **WHEN** the user saves an incomplete or invalid configuration
- **THEN** the system rejects the change
- **AND** the validation errors identify which field or capability is missing

### Requirement: Minimal Home Assistant Add-on Options Usage
The system SHALL minimize reliance on Home Assistant add-on options for HEMS feature configuration.

#### Scenario: Home Assistant add-on options remain operational only
- **WHEN** the HEMS add-on exposes Home Assistant add-on options
- **THEN** those options are limited to operational or recovery concerns such as debug behavior or bootstrap settings
- **AND** asset, module, policy, and planning configuration remain in the web interface

### Requirement: Home Assistant Connectivity Status
The system SHALL expose HEMS runtime health and Home Assistant connectivity status to support setup and diagnostics.

#### Scenario: Healthy startup
- **WHEN** the HEMS add-on starts successfully and can reach the Home Assistant API
- **THEN** the system reports itself as healthy
- **AND** the web interface shows Home Assistant connectivity as available

#### Scenario: Home Assistant unavailable
- **WHEN** the Home Assistant API is unavailable during startup or runtime
- **THEN** the system reports degraded health
- **AND** planning that depends on Home Assistant state is blocked with a visible reason
