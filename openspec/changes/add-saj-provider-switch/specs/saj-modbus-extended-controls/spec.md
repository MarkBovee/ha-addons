## ADDED Requirements

### Requirement: Capability-gated advanced controls
The Modbus backend SHALL expose advanced controls only when their write path is mapped and validated.

#### Scenario: Optional Modbus controls are mapped
- **WHEN** the Modbus backend has validated mappings for advanced controls
- **THEN** it SHALL publish those controls as available capabilities instead of bundling them into the base parity path

#### Scenario: Optional Modbus controls are not mapped
- **WHEN** the required advanced-control entities are missing or unvalidated
- **THEN** the add-on SHALL keep the controls disabled and SHALL not advertise them as supported

### Requirement: Export limit support
The Modbus backend SHALL support export limiting as an exposed advanced control when the mapped entity is available.

#### Scenario: Zero-export is requested
- **WHEN** a valid export-limit request is sent through the advanced-control path
- **THEN** the add-on SHALL translate it into the mapped Modbus export-limit write and verify the write result

#### Scenario: Negative price strategy needs export suppression
- **WHEN** a strategy requests export suppression during negative-price periods
- **THEN** the backend SHALL expose export limit as an available control path when the mapped entity exists

### Requirement: Passive mode support
The Modbus backend SHALL support passive charge and passive discharge as optional advanced controls only after mapping and validation.

#### Scenario: Passive mode capability is enabled
- **WHEN** passive mode entities are mapped and validated
- **THEN** the add-on SHALL expose passive-mode capability separately from the base TOU schedule path

### Requirement: Unsupported features remain explicitly unsupported
The system SHALL not claim support for unvalidated Modbus behaviors.

#### Scenario: PV-off is requested without a validated control path
- **WHEN** there is no confirmed register or Home Assistant write path for disabling PV generation safely
- **THEN** the add-on SHALL mark PV-off as unsupported instead of exposing a control that only approximates the behavior

#### Scenario: Experimental passive-grid behavior is discussed
- **WHEN** an advanced feature depends on behavior that upstream documents as unreliable or edge-case-specific
- **THEN** the add-on SHALL keep that feature behind an explicit experimental label until real-device validation is complete
