## Phase 1: Plan & Spec
- [x] 1.1 Finalize minimal config surface (power/SOC, TopX, adaptive, solar flag, temperature sensors, price sensor fixed) - **DONE [12:00]**
- [x] 1.2 Write delta spec for `hems` capability (ADDED requirements) - **DONE [12:00]**

## Phase 2: Scaffold Add-on
- [x] 2.1 Create `hems/` structure (Dockerfile, run.sh, requirements.txt, config.yaml, README.md, app/) - **DONE [12:00]**
- [x] 2.2 Copy/shared sync helpers into `hems/shared` - **DONE [12:00]**

## Phase 3: Implement Core Logic
- [x] 3.1 Implement Range-Based scheduling/adaptive monitor (Python) with 1m cadence - **DONE [12:00]**
- [x] 3.2 Integrate price helper (HA sensor), battery-api client, SOC/power sensors, optional solar helper - **DONE [12:00]**
- [x] 3.3 Surface HA entities (status, next charge/discharge, adaptive power) via REST/MQTT - **DONE [12:00]**

## Phase 4: Validate & Docs
- [x] 4.1 Update README with setup, sensors, defaults - **DONE [12:00]**
- [x] 4.2 Validate config schema and run add-on lint/checks if available - **DONE [12:00]**
- [x] 4.3 Update proposal status and mark tasks complete - **DONE [12:00]**
