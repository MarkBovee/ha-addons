# Proposal: Zonneplan 2026 Pricing Logic

**Version:** 1.0
**Status:** 100%
**Date:** 2026-01-01

## Executive Summary
Update the Energy Prices add-on to support the Zonneplan (NL) dynamic energy contract pricing model effective from January 1, 2026. This model accounts for the continuation of the netting scheme (salderingsregeling) in 2026.

## What's Changing

| Feature | Before | After |
| :--- | :--- | :--- |
| **Import Price** | `(spot * vat) + markup + tax` | `(spot + markup + tax) * vat` |
| **Export Price** | Same formula as import | `(spot + fixed_bonus) * vat` + Solar Bonus |
| **Solar Bonus** | None | +10% on positive spot prices during daylight |
| **Configuration** | Markup, Tax | Fixed Bonus, Bonus %, Lat/Lon |

## Benefits
- Accurate pricing for Zonneplan customers in 2026.
- Support for solar bonus calculations based on daylight.
- Configurable location for accurate sunrise/sunset times.

## Success Criteria
- Import prices match Zonneplan formula.
- Export prices include solar bonus during daylight hours when spot price is positive.
- Export prices do not include bonus at night or when spot price is negative.
- VAT is applied correctly to the total sum for both import and export (due to netting).

## Risk Assessment
- **Breaking Change:** The import price formula has changed. Users with other contracts might need to adjust their markup/tax settings to match the new formula `(spot + markup + tax) * vat` vs the old `(spot * vat) + markup + tax`.
- **Dependencies:** Added `astral` library for sun calculations.
