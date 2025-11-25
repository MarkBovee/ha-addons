# Energy Prices Add-on Proposal

**Version:** 1.0  
**Status:** 🟡 **IN PROGRESS - 83% COMPLETE**  
**Created:** 2025-11-25  
**Last Updated:** 2025-11-25  
**Target Completion:** TBD

---

## Why

### Problem Statement
Currently, there is no standardized way to fetch and process electricity prices in Home Assistant for the Dutch market. Users who want to optimize energy consumption based on dynamic pricing must:
1. Manually integrate with Nord Pool or energy provider APIs
2. Create complex automations to calculate final prices (including VAT, grid fees, taxes)
3. Duplicate price data across multiple automations and add-ons
4. Lack visibility into price trends and classifications (low/medium/high)

This creates fragmentation, inconsistent price calculations, and prevents building sophisticated energy-aware automations.

### User Pain Points
- **Manual Integration:** Users must write custom scripts to fetch Nord Pool prices
- **Price Calculation Complexity:** Energy contracts include VAT, grid fees, and energy taxes that vary per provider
- **No Standardization:** Each automation calculates prices differently, leading to inconsistencies
- **Limited Visibility:** No easy way to see if current price is "low" or "high" relative to forecast
- **Dependency Chain:** Future add-ons (battery optimizer, appliance scheduler) need reliable price data

## Executive Summary

Create a new Home Assistant add-on that fetches Nord Pool day-ahead electricity prices and applies user-defined Jinja2 templates to calculate final import and export prices in cents/kWh. This add-on serves as the foundation for energy-aware automation by providing consistent, real-time pricing data to other add-ons and automations.

### Key Goals
1. Fetch 15-minute interval prices from Nord Pool API for Dutch market (NL)
2. Allow flexible price calculations via Jinja2 templates (VAT, grid fees, energy tax)
3. Expose import/export prices with 48-hour forecast as Home Assistant entities
4. Compute price percentiles (P20/P40/P60) and price level classifications
5. Provide reliable, cacheable price data for downstream automations

---

## What's Changing

| Aspect | Before | After |
|--------|--------|-------|
| **Price Data Source** | None | Nord Pool Day-Ahead API with 15-min intervals |
| **Price Calculation** | N/A | User-defined Jinja2 templates for import/export |
| **Data Format** | N/A | Cents/kWh with UTC timestamps, 4 decimal precision |
| **HA Entities** | None | `sensor.ep_price_import`, `sensor.ep_price_export`, `sensor.ep_price_level` |
| **Configuration** | N/A | YAML config with templates, region, timezone, percentiles |
| **Dependencies** | N/A | Requires `requests`, `Jinja2` |

---

## Benefits

### For Users
- **Transparency**: See exactly how final prices are calculated via editable templates
- **Flexibility**: Customize templates to match energy contract specifics (VAT, fees, taxes)
- **Automation**: Build energy-aware automations using price level sensors (None/Low/Medium/High)
- **Cost Savings**: Shift energy usage to low-price periods based on real-time forecasts

### For System
- **Foundation**: Provides consistent price data for future add-ons (battery optimizer, appliance guard)
- **Reliability**: Caching and fallback mechanisms prevent service disruptions
- **Performance**: Efficient 15-minute granularity with hourly API fetches
- **Maintainability**: Clean separation between API client, template processor, and entity management

---

## Scope

### In Scope
- Nord Pool API integration (day-ahead prices for NL market)
- Jinja2 template processor with `marktprijs` variable exposure
- Template validation at add-on startup (fail-fast on invalid templates)
- Default template examples in documentation (VAT 21%, grid fees, energy tax)
- Price conversion: EUR/MWh → cents/kWh with 4 decimal precision rounding
- Home Assistant entity creation/updates (import, export, price level)
- Price curve attributes (48-hour forecast with UTC timestamps)
- Percentile calculations (P05, P20, P40, P60, P80, P95) from import prices
- Price level classification: None (<P20), Low (P20-P40), Medium (P40-P60), High (>P60)
- Configurable fetch interval (default: 60 minutes)
- Graceful shutdown handling (SIGTERM/SIGINT)

### Out of Scope
- Historical price storage (only current + next day)
- Price predictions or forecasting (only published Nord Pool data)
- Multi-region support (focus on NL for v1.0)
- Fallback to user-provided sensors
- Custom percentile thresholds (hardcoded P20/P40/P60 for v1.0)
- Web UI or REST API endpoints (HA entities only)
- Integration with battery systems or appliances (handled by other add-ons)

---

## Risk Assessment

### Technical Risks

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Nord Pool API unavailable | Medium | High | Cache last successful fetch; log errors; retry with backoff |
| Invalid Jinja2 templates | High | High | Validate at startup; fail-fast with clear error messages |
| Template runtime errors | Medium | Medium | Use Jinja2 sandbox; catch exceptions; log with template context |
| Timezone confusion (UTC/CET) | Medium | Medium | Store all times in UTC; document clearly; add timezone metadata to entities |
| Price unit errors (MWh/kWh) | Low | High | Add unit tests; document conversion formula; log raw and converted values |
| HA API failures | Low | Medium | Retry entity updates; log failures; continue operation |

### Operational Risks
- **User Misconfiguration**: Invalid templates could break price calculations
  - *Mitigation*: Provide working default examples; validate syntax at startup
- **API Rate Limiting**: Excessive fetches could trigger rate limits
  - *Mitigation*: Default 60-minute interval; respect HTTP 429 responses; implement exponential backoff

---

## Implementation Plan

### Phase 1: Add-on Structure & Configuration (0% → 17%)
- Create `energy-prices/` directory with standard add-on files
- Define `config.yaml` with options schema (delivery_area, timezone, templates, etc.)
- Create `Dockerfile` and `run.sh` following charge-amps-monitor pattern
- Set up `requirements.txt` with `requests` and `Jinja2` dependencies

### Phase 2: Nord Pool API Client (17% → 33%)
- Implement `app/nordpool_api.py` with `NordPoolApi` class
- Add `fetch_prices(date, delivery_area, currency)` method
- Handle HTTP 200 (data available) and 204 (not published yet) responses
- Parse `multiAreaEntries` JSON structure
- Convert EUR/MWh to cents/kWh (multiply by 0.1)
- Create `PriceInterval` model in `app/models.py` with UTC timestamps

### Phase 3: Template Processor (33% → 50%)
- Implement `app/price_calculator.py` with `TemplateProcessor` class
- Add template validation logic (Jinja2 syntax check at init)
- Expose `marktprijs` variable (cents/kWh) in template context
- Implement `calculate_price(marktprijs_cents)` method using Jinja2 sandbox
- Round output to 4 decimal places
- Handle template rendering errors gracefully with logging

### Phase 4: Main Loop & Entity Management (50% → 67%)
- Implement `app/main.py` with signal handlers (SIGTERM, SIGINT)
- Create main loop with configurable fetch interval
- Fetch today's and tomorrow's prices from Nord Pool API
- Calculate import/export prices using templates for each 15-min interval
- Compute percentiles (P05, P20, P40, P60, P80, P95) from import prices
- Determine current price level classification (None/Low/Medium/High)
- Create/update HA entities with price curves in attributes

### Phase 5: Testing & Documentation (67% → 83%)
- Create `run_local.py` script with `.env.example` file
- Test template validation (valid/invalid syntax)
- Test price conversion accuracy (EUR/MWh → cents/kWh)
- Test percentile calculations with sample data
- Verify entity creation and attribute structure in HA dev instance
- Write comprehensive README with template examples

### Phase 6: Integration & Polish (83% → 100%)
- Update root `README.md` and `repository.json`
- Add add-on to Home Assistant add-on store metadata
- Test complete flow: fetch → template → entities → attributes
- Verify graceful shutdown behavior
- Final testing with real Nord Pool API data
- Create demo video/screenshots for documentation

---

## Success Criteria

- [ ] Add-on installs successfully via HA Supervisor
- [ ] Nord Pool API fetches return 96 price intervals per day
- [ ] Template validation catches syntax errors at startup
- [ ] Import/export prices calculated correctly with 4-decimal precision
- [ ] Percentiles computed accurately from price distribution
- [ ] HA entities created with correct state and attributes
- [ ] Price curves contain 48 hours of UTC-timestamped data
- [ ] Price level sensor updates based on P20/P40/P60 thresholds
- [ ] Add-on handles graceful shutdown (SIGTERM/SIGINT)
- [ ] Documentation includes working template examples
- [ ] No errors in logs during normal operation

---

## Timeline

| Milestone | Target Date | Status |
|-----------|-------------|--------|
| Proposal Approval | 2025-11-25 | ⏳ Pending |
| Phase 1 Complete | TBD | ⏳ Pending |
| Phase 2 Complete | TBD | ⏳ Pending |
| Phase 3 Complete | TBD | ⏳ Pending |
| Phase 4 Complete | TBD | ⏳ Pending |
| Phase 5 Complete | TBD | ⏳ Pending |
| Phase 6 Complete | TBD | ⏳ Pending |
| Deployment | TBD | ⏳ Pending |

---

## Dependencies

### Technical Dependencies
- Python 3.12+
- `requests>=2.31.0` (HTTP client)
- `Jinja2>=3.1.0` (template engine)
- Home Assistant Supervisor with API access
- Nord Pool Day-Ahead API availability

### Project Dependencies
- None (this is the first energy-related add-on)

### Future Dependents
- Battery Optimizer add-on (will consume price data)
- Appliance Guard add-on (will use price levels)
- Water Heater Scheduler add-on (will use price curves)

---

## Notes

### Template Design Decisions
1. **Why Jinja2 templates instead of fixed config values?**
   - Maximum flexibility for different energy contracts
   - Users can see exactly how prices are calculated
   - Easy to adjust for changing tariffs without code changes
   
2. **Why 4 decimal places for cents?**
   - Balances precision (0.01 cent accuracy) with readability
   - Matches typical energy billing precision
   - Prevents floating-point rounding issues in automations

3. **Why fail-fast on invalid templates?**
   - Better than silently producing wrong prices
   - Forces users to fix configuration immediately
   - Clear error messages guide troubleshooting

### API Design Decisions
1. **Why store timestamps in UTC?**
   - Avoids DST confusion (CET ↔ CEST transitions)
   - Aligns with Nord Pool API format
   - Standard practice for time-series data
   
2. **Why fetch both today and tomorrow?**
   - Tomorrow's prices available at ~13:00 CET
   - Enables 48-hour forecast for planning automations
   - Handles midnight transitions smoothly

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2025-11-25 | Initial proposal created |
