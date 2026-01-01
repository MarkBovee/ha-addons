# Pricing Specification

## ADDED Requirements

### Requirement: Zonneplan 2026 Import Pricing
The system SHALL calculate import prices using the formula: `(spot_price + markup + energy_tax) * vat_multiplier`.

#### Scenario: Standard Import Calculation
- **WHEN** spot price is 0.10, markup 0.02, tax 0.1108, vat 1.21
- **THEN** price is (0.10 + 0.02 + 0.1108) * 1.21 = 0.2793

### Requirement: Zonneplan 2026 Export Pricing
The system SHALL calculate export prices including VAT (due to netting) and apply a solar bonus during daylight hours for positive prices.

#### Scenario: Daylight Positive Price
- **WHEN** spot price is 0.10, fixed bonus 0.02, bonus 10%, daylight is TRUE
- **THEN** base is 0.10 + 0.02 = 0.12
- **AND** bonus applied: 0.12 * 1.10 = 0.132
- **AND** VAT applied: 0.132 * 1.21 = 0.1597

#### Scenario: Night Positive Price
- **WHEN** spot price is 0.10, fixed bonus 0.02, daylight is FALSE
- **THEN** base is 0.10 + 0.02 = 0.12
- **AND** no bonus applied
- **AND** VAT applied: 0.12 * 1.21 = 0.1452

#### Scenario: Negative Price
- **WHEN** spot price is -0.05
- **THEN** price is -0.05 (no bonus, no fixed fee added in base calculation for bonus?)
- **WAIT** User said: "Bij negatieve spotprijzen: geen zonnebonus, exportvergoeding = spotprijs".
- **AND** VAT applied: -0.05 * 1.21 = -0.0605 (Netting implies VAT follows the price)

## MODIFIED Requirements

### Requirement: Import Price Formula
The system SHALL calculate the import price by applying VAT to the sum of spot price, markup, and energy tax.

#### Scenario: Modified Import Calculation
- **WHEN** spot price is 0.10, markup 0.02, tax 0.1108, vat 1.21
- **THEN** price is (0.10 + 0.02 + 0.1108) * 1.21 = 0.2793
