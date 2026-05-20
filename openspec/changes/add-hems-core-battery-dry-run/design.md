## Context

This repository already contains stable Home Assistant add-ons for price ingestion, battery control, battery optimization, charger monitoring, and water heater scheduling. Those add-ons solve individual problems well, but each add-on owns its own configuration model, decision loop, and output entities. The requested HEMS direction changes the architecture from separate optimizers into a single add-on that can be installed on other Home Assistant systems without custom code and can coordinate multiple asset types under one total energy plan.

The first release is intentionally constrained to onboarding, UI, asset mapping, dry-run simulation, and the first module: battery optimization. The design must still support future modules such as water heater, EV charging, heat pump control, solar surplus routing, and peak shaving. The platform runs on Home Assistant Supervisor add-on infrastructure, should fit Raspberry Pi-class hardware, and should preserve the existing production add-ons while HEMS is introduced in parallel.

The HEMS web interface is also a first-class product requirement. Home Assistant add-on options are too limited for discovery-driven setup, asset capability mapping, module strategy tuning, decision explainability, diagnostics, and history. The design therefore treats the web UI as the primary user-facing control plane and keeps Home Assistant add-on settings minimal and operational only.

## Goals / Non-Goals

**Goals:**
- Define a new HEMS add-on architecture that keeps all future orchestration inside one add-on.
- Use Python for backend and decision logic so existing battery logic can be migrated pragmatically.
- Support a web UI for onboarding, asset setup, module management, dry-run visibility, and explainability.
- Make the web UI the complete functional configuration surface for HEMS setup and daily operation.
- Normalize Home Assistant entities into reusable asset capabilities instead of hard-coding vendor-specific flows.
- Make dry-run the default execution mode so users can safely validate mappings and decisions before automation.
- Ensure modules produce proposals while a central decision engine produces the final total plan.
- Make battery the first production-focused module under the new architecture.

**Non-Goals:**
- Rebuild or replace the current production add-ons as part of this change.
- Deliver full auto-control for all assets in the first implementation wave.
- Solve every vendor-specific integration edge case up front.
- Introduce cloud services, mobile apps, or machine-learning optimization.
- Deliver water heater, EV, or heat pump modules in this initial change.
- Mirror the full HEMS configuration surface inside Home Assistant add-on options.

## Decisions

### Decision: Build HEMS as a new add-on rather than extending an existing add-on

The HEMS should be introduced as its own add-on so the current stable add-ons remain unchanged while the new platform evolves. This avoids coupling new architecture work to existing production behavior and lets HEMS become the future orchestration layer without breaking current installs.

Alternatives considered:
- Extend `battery-manager`: rejected because its scope and config model are already battery-specific.
- Merge all add-ons immediately: rejected because it creates unnecessary migration and regression risk.

### Decision: Keep backend, module logic, and decision logic in Python

The backend should stay in Python because the battery logic already exists in Python and the repository conventions, deployment model, and domain code are already optimized around Python add-ons. This reduces migration cost and makes the first module much faster to deliver.

Alternatives considered:
- Full TypeScript stack: rejected because it would force battery logic migration before value is delivered.
- Separate languages per module: rejected because it increases complexity and weakens consistency.

### Decision: Use a web UI with a separate frontend layer

The HEMS requires onboarding, entity selection, asset management, module toggles, timelines, and explainability views that are difficult to deliver cleanly through add-on options alone. A dedicated web UI should therefore be part of the HEMS architecture from the start.

Alternatives considered:
- Add-on options only: rejected because it cannot support discovery-driven setup and dry-run explainability well.
- Home Assistant dashboard package only: rejected because the HEMS still needs its own setup and management surface.

### Decision: Use a React and TypeScript frontend with shadcn/ui primitives

The frontend should use React and TypeScript to keep the UI predictable, strongly typed, and maintainable as the HEMS grows into a multi-screen product. The recommended UI stack is:
- React + TypeScript
- Vite for development and build
- Tailwind CSS for styling
- shadcn/ui for composable UI primitives and form-heavy app structure
- TanStack Router for explicit application routing
- TanStack Query for API state and polling
- React Hook Form + Zod for validated forms and settings workflows
- Recharts through shadcn chart wrappers for planning and timeline charts
- Lucide icons for consistent iconography

This stack fits a dashboard-style application with many forms, panels, tables, drawers, dialogs, and charts, while keeping control over the final look and avoiding rigid enterprise component suites.

Alternatives considered:
- MUI: rejected because it imposes too much default visual language and tends to feel generic for a product UI.
- Ant Design: rejected because it is heavier and stylistically less aligned with a focused custom dashboard.
- Plain Tailwind without component primitives: rejected because the project will repeat complex patterns for forms, sheets, dialogs, navigation, and tables.
- Next.js: rejected because server rendering is not needed for an internal add-on UI and would add deployment complexity.

### Decision: Make the web UI the primary configuration and operations surface

All functional HEMS settings should live in the web interface, including asset setup, module behavior, global policies, planning visibility, diagnostics, and history. Home Assistant add-on options should be limited to minimal operational bootstrap settings such as startup behavior, debug controls, or recovery toggles. This keeps the user experience coherent and avoids duplicating configuration across two systems.

Alternatives considered:
- Split settings between HA add-on options and the web UI: rejected because it creates confusion and hidden state.
- Keep module-specific settings outside the HEMS UI: rejected because the product needs a single operational control plane.

### Decision: Organize the UI around operations and explainability instead of raw forms

The main navigation should prioritize daily understanding and control rather than configuration forms alone. The HEMS UI should center on a dashboard, assets, modules, planning, history, diagnostics, and settings. Forms still exist, but they should live inside those operational areas and support setup and tuning without making the product feel like an add-on schema editor.

Alternatives considered:
- Form-first configuration UI: rejected because it weakens trust and makes the product feel technical instead of operational.
- Single giant setup page: rejected because the system will grow to multiple assets and modules.

### Decision: Use a dark-first dashboard visual system with strong status contrast

The HEMS UI should default to a dark dashboard-oriented visual system because operators will spend most of their time reading status, charts, warnings, and timelines. The UI should use high-contrast neutrals with restrained accent colors for energy state, warnings, and action outcomes instead of decorative visual effects. A muted industrial palette with orange for energy activity, green for healthy or selected actions, blue for information, and red for blocks or errors fits the product domain and supports fast scanning.

Alternatives considered:
- Light-first admin UI: rejected because dense timeline and status views are less comfortable in the intended dashboard context.
- Highly stylized glassmorphism: rejected because readability and density matter more than novelty.

### Decision: Use guided onboarding and layered complexity

The first user experience should be a setup wizard that discovers entities, helps create assets, validates mappings, enables the first module, and lands the user in dry-run mode. After onboarding, the UI should continue to support both simple and advanced usage by showing strong defaults first and moving advanced or expert controls behind secondary sections.

Alternatives considered:
- Require manual setup from settings pages only: rejected because it raises the barrier for other users.
- Expose all configuration at once: rejected because it creates noise and makes validation harder to understand.

### Decision: Separate asset constraints, module strategy, and global policy

The UI and backend data model should distinguish between three layers of configuration:
- asset configuration for what a device is and what it can do
- module configuration for how optimization logic should behave
- global policy for home-wide priorities and fallback behavior

This separation prevents battery constraints, battery strategy, and whole-home planning policy from becoming mixed into one oversized settings model.

Alternatives considered:
- Single flat settings model: rejected because it will not scale past the first module.
- Module-owned global policy settings: rejected because cross-module planning needs one shared policy source.

### Decision: Make explainability and diagnostics first-class UI features

The UI should not only show planned actions, but also why actions were selected, blocked, or deferred, which data inputs were used, and whether those inputs were fresh or degraded. Diagnostics should therefore be a dedicated product area rather than an afterthought in logs.

Alternatives considered:
- Keep reasoning only in backend logs: rejected because it is not usable for normal installs.
- Show only final actions with no blocked history: rejected because trust in dry run depends on visibility into non-actions as well.

### Decision: Build the UI from reusable app-shell and workspace patterns

The frontend should use a small set of repeated layout patterns so the product remains coherent as modules are added. The main patterns are:
- app shell with persistent top status bar and left navigation
- workspace list/detail layout for assets and modules
- timeline/detail layout for planning and history
- diagnostics cards plus raw detail drawers for support cases

This keeps navigation stable and allows individual screens to grow without rethinking layout rules each time.

Alternatives considered:
- Unique layout per page: rejected because it would make the app feel fragmented.
- Single-page dashboard only: rejected because setup, diagnostics, and history need focused workflows.

Implementation note:
- `ui-wireframes.md` in this change is the detailed reference for routes, page composition, reusable component patterns, form behaviors, and responsive layout rules.

### Decision: Model installations around assets and capabilities

Each installation should configure assets such as battery, solar, grid, or water heater. Each asset stores mapped Home Assistant entities and the capabilities those entities expose, such as `soc.read`, `power.read`, or `target_temperature.set`. This creates a universal configuration model and avoids hard-coding behavior around one entity naming scheme.

Alternatives considered:
- Entity-first configuration only: rejected because it spreads logic across raw entity IDs and is hard to validate.
- Vendor profile only: rejected because the stated goal is universal Home Assistant compatibility.

### Decision: Separate module proposals from final decisions

Modules should not directly control assets or finalize schedules. Each enabled module should produce proposals, constraints, expected impact, and explanations. The central decision engine should then combine proposals across all active modules and produce one final plan. This preserves future cross-module coordination when battery, EV, boiler, and heat pump modules all become active.

Alternatives considered:
- Let each module self-execute: rejected because modules would conflict once multiple assets are active.
- Build only a global optimizer with no modules: rejected because it would slow delivery and reduce modularity.

### Decision: Make dry-run the default operating model for the first release

The first HEMS release should read state, simulate actions, explain decisions, and expose timelines without issuing real control commands. This reduces installation risk, makes the product portable to other users, and gives the team a clean validation layer before automation is introduced.

Alternatives considered:
- Enable automation from the start: rejected because setup and capability mismatches will be common in early installs.
- Observation only with no simulated actions: rejected because it does not build trust in the decision engine.

### Decision: Use phased storage starting with local persisted data

Configuration, mappings, UI state, and dry-run artifacts should persist under `/data`. The initial implementation may start with structured JSON files or a lightweight SQLite database, as long as the internal service boundary allows later evolution. The design should not require an external database service.

Alternatives considered:
- External database: rejected because it complicates Home Assistant addon installation.
- In-memory only: rejected because mappings and state must survive restarts.

### Decision: Start with battery as the first module under a generic module contract

Battery is the most valuable first module because existing logic already covers dynamic prices, solar, grid awareness, and schedule reasoning. The HEMS battery module should reuse that domain knowledge but adapt it to normalized assets, module proposals, and dry-run-first behavior.

Alternatives considered:
- Water heater first: rejected because battery has more reusable logic and broader HEMS leverage.
- Build multiple modules at once: rejected because one module at a time is the agreed rollout strategy.

## Risks / Trade-offs

- Capability normalization may be harder than expected across real Home Assistant installs → Start with a strict battery asset profile, validation rules, and partial-support states instead of pretending every mapping is valid.
- Reusing battery-manager logic may import too much add-on-specific behavior → Extract only domain logic and reframe integrations behind HEMS interfaces.
- A web UI adds build and packaging complexity to a Python add-on → Keep the first UI focused on onboarding, asset setup, and dry-run visibility rather than broad dashboard scope.
- A broad UI surface can become too ambitious for the first release → Deliver a clear v0.1 navigation skeleton and implement the deepest detail first for dashboard, assets, modules, planning, and lightweight diagnostics.
- Dry-run predictions may diverge from real behavior when source entities are stale or incomplete → Surface data freshness, missing capabilities, and blocked decisions explicitly in the UI and status outputs.
- Central decision engine design may be overbuilt too early → Start with a simple proposal aggregation and priority-based resolver that is enough for one battery module but scales to more modules.

## Migration Plan

1. Add the new HEMS add-on as a separate directory and package it independently from the existing add-ons.
2. Implement the HEMS core, asset registry, and dry-run interfaces without changing current production add-ons.
3. Port or adapt battery optimization logic into the HEMS battery module contract.
4. Release the HEMS initially in dry-run mode only.
5. Validate entity mapping, simulation output, and decision explainability in local and Home Assistant test environments.
6. Establish the web UI as the single functional configuration surface and keep Home Assistant add-on settings minimal.
7. Introduce later modules and execution modes in follow-up changes after the dry-run foundation proves stable.

Rollback is straightforward because this change introduces a new add-on instead of modifying existing production add-ons. If the HEMS is not ready, users simply keep using the current add-ons.

## Open Questions

- Should the first persisted state layer use JSON files only or move directly to SQLite for assets, events, and timeline storage?
- Should the initial web UI be served directly by the Python backend or built as a separately compiled static frontend bundled into the add-on image?
- How much of the existing battery-manager logic can be shared cleanly without dragging along its old entity contracts and operational assumptions?
- Which Home Assistant write paths should become the default control abstraction later: service calls, MQTT discovery entities, or a mix per asset capability?
- How much history and diagnostic retention should be exposed in v0.1 before the UI becomes too heavy?
