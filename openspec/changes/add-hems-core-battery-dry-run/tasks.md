## 1. Change Foundation

- [ ] 1.1 Create the new `hems` add-on directory with Home Assistant add-on metadata, image build files, and base runtime entrypoint.
- [ ] 1.2 Define the initial backend project structure for API, core services, modules, assets, persistence, and shared utilities.
- [ ] 1.3 Define the initial frontend project structure using React, TypeScript, Vite, Tailwind CSS, shadcn/ui, TanStack Router, TanStack Query, React Hook Form, and Zod.
- [ ] 1.4 Translate the UI wireframes into reusable app-shell, workspace, and detail-view component patterns.

## 2. Core Runtime

- [ ] 2.1 Implement HEMS configuration loading, persisted state initialization, and graceful startup and shutdown handling.
- [ ] 2.2 Implement global operating modes including `disabled`, `observe`, `dry_run`, `advisory`, and `auto`, with `dry_run` as the default first-run mode.
- [ ] 2.3 Implement runtime health and Home Assistant connectivity status reporting for the UI and diagnostics.

## 3. Asset Registry And Mapping

- [ ] 3.1 Implement the asset registry model with support for asset types, mapped entities, capabilities, validation state, and per-asset operating mode.
- [ ] 3.2 Implement Home Assistant entity discovery for setup flows and candidate selection.
- [ ] 3.3 Implement capability-based mapping validation with clear diagnostics for missing, invalid, stale, and optional capabilities.
- [ ] 3.4 Implement API endpoints and persistence for creating, updating, validating, listing, and deleting assets.

## 4. Decision Engine And Dry Run

- [ ] 4.1 Implement the module contract for proposal generation, explanations, and constraint reporting.
- [ ] 4.2 Implement the central decision engine that gathers module proposals and produces one final plan for the active horizon.
- [ ] 4.3 Implement conflict handling, hard-constraint blocking, and reason capture in final plan resolution.
- [ ] 4.4 Implement dry-run execution behavior that records simulated actions without issuing control writes.
- [ ] 4.5 Implement decision history retention, decision timeline data, and explanation payloads for the UI.
- [ ] 4.6 Implement global policy configuration for strategy profiles, priorities, fallback behavior, and planning horizon control.

## 5. Battery Module

- [ ] 5.1 Define the battery asset capability profile, including required and optional mappings needed for battery planning.
- [ ] 5.2 Implement normalized battery state readers that translate mapped Home Assistant entities into battery module inputs.
- [ ] 5.3 Port or adapt reusable battery-manager planning logic behind HEMS battery interfaces.
- [ ] 5.4 Implement battery dry-run proposal generation for charge, discharge, and protection-driven no-action outcomes.
- [ ] 5.5 Implement structured battery proposal explanations and blocked-action reasons.
- [ ] 5.6 Implement persisted battery module strategy settings for reserve behavior, solar-aware charging, negative-price handling, and planning aggressiveness.

## 6. Web Interface

- [ ] 6.1 Implement the main application shell with persistent system mode, health, warnings, and global pause controls.
- [ ] 6.2 Implement the first-run onboarding flow for Home Assistant connectivity, entity discovery, initial asset creation, validation, first module enablement, and dry-run start.
- [ ] 6.3 Implement dashboard views for current status, active assets and modules, current decision, and next-horizon plan summary.
- [ ] 6.4 Implement asset management screens with list view, asset detail workspace, entity mapping, capability status, constraints, and diagnostics.
- [ ] 6.5 Implement module management screens with module enablement, strategy settings, module status, and linked asset visibility.
- [ ] 6.6 Implement planning views with final plan timeline, blocked and deferred action visibility, and detailed explainability panels.
- [ ] 6.7 Implement diagnostics screens for connectivity, mapping health, module health, planner health, and support-friendly inspection data.
- [ ] 6.8 Implement history views for prior planning cycles, key outcomes, and drill-down into past decisions.
- [ ] 6.9 Implement settings screens for global policy, planning horizon, operational preferences, and backup or restore controls while keeping functional configuration out of Home Assistant add-on options.

## 7. Verification

- [ ] 7.1 Add backend tests for asset validation, module proposal contracts, decision engine resolution, and battery dry-run planning.
- [ ] 7.2 Add frontend tests for onboarding, asset mapping flows, and dry-run status rendering.
- [ ] 7.3 Verify the add-on locally and in a Home Assistant test environment with representative battery-related entities and dry-run scenarios.
- [ ] 7.4 Document the HEMS architecture, setup expectations, and dry-run-first rollout strategy.
