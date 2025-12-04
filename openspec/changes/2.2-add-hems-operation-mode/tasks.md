# Tasks: Add HEMS Operation Mode

## Phase 1: Configuration & Mode Infrastructure
- [ ] 1.1 Add `operation_mode` config option to `config.yaml` (list: standalone|hems, default: standalone)
- [ ] 1.2 Add `price_threshold` config option to `config.yaml` (float, default: 0.25)
- [ ] 1.3 Update `AutomationConfig` dataclass with new fields
- [ ] 1.4 Add mode validation in main.py startup
- [ ] 1.5 Verify build compiles and add-on starts with new config

## Phase 2: Standalone Mode Enhancements
- [ ] 2.1 Modify `PriceSlotAnalyzer` to support price threshold filtering
- [ ] 2.2 Implement unique price level selection (group slots by price, pick top X levels)
- [ ] 2.3 Update `analyze_prices()` to apply threshold before selection
- [ ] 2.4 Add `price_threshold_active` attribute to status (shows if threshold filtered any slots)
- [ ] 2.5 Write unit tests for unique price selection logic
- [ ] 2.6 Write unit tests for price threshold filtering

## Phase 3: HEMS Mode - MQTT Subscriber
- [ ] 3.1 Create `HEMSScheduleHandler` class for MQTT message processing
- [ ] 3.2 Define schedule payload schema and validation
- [ ] 3.3 Subscribe to `hems/charge-amps/{connector_id}/schedule/set` topic
- [ ] 3.4 Subscribe to `hems/charge-amps/{connector_id}/schedule/clear` topic
- [ ] 3.5 Implement schedule application from HEMS payload
- [ ] 3.6 Handle `expires_at` - auto-clear expired schedules
- [ ] 3.7 Write unit tests for MQTT message parsing and validation

## Phase 4: HEMS Mode - Status Publisher
- [ ] 4.1 Define HEMS status payload structure
- [ ] 4.2 Publish to `hems/charge-amps/{connector_id}/status` on state changes
- [ ] 4.3 Include schedule_source, ready_for_schedule, last_hems_command_at
- [ ] 4.4 Publish periodic status updates (configurable interval)

## Phase 5: Mode Switching & Sensors
- [ ] 5.1 Implement mode switch handling (clear schedule, reinitialize)
- [ ] 5.2 Add `sensor.ca_schedule_source` entity (standalone|hems|none)
- [ ] 5.3 Add `sensor.ca_hems_last_command` entity (timestamp)
- [ ] 5.4 Add `binary_sensor.ca_price_threshold_active` entity
- [ ] 5.5 Update existing schedule status sensor with source info

## Phase 6: Documentation & Testing
- [ ] 6.1 Update charge-amps-monitor README with operation modes
- [ ] 6.2 Document HEMS MQTT contract (topics, payloads)
- [ ] 6.3 Add configuration examples for both modes
- [ ] 6.4 Integration test: standalone mode with threshold
- [ ] 6.5 Integration test: HEMS mode schedule application
- [ ] 6.6 Bump version and update CHANGELOG

## Dependencies
- Phase 2 can run in parallel with Phase 3-4
- Phase 5 depends on Phase 3-4 completion
- Phase 6 depends on all other phases
