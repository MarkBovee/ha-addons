# Prompt voor een nieuwe sessie: HEMS verder (28 okt 2026)

Kopieer alles onder de streep als eerste bericht in een nieuwe Claude Code-sessie in deze repo.

---

Je gaat verder met HEMS, de Home Assistant-integratie `hems` in `/mnt/work/Projects/Personal/ha-addons`, worktree `.claude/worktrees/hems`. Antwoord in het Nederlands, kort en technisch precies. Alle tekst in HA en het paneel is Engels. Commit, push, merge of installeer alleen na mijn expliciete ja; test-deploys in dry-run mogen (`python3 hems/deploy.py`). HA herstarten doe ik zelf.

## Doel
HEMS vervangt de losse add-ons (battery-manager, energy-prices, water-heater-scheduler) en gaat van dry-run naar echte aansturing. Plan: `docs/hems/live-transition-plan.md` (fasen 0–6, route B: HEMS schrijft de SAJ-entiteiten zelf).

## Stand
- **Branch** `feature/hems-dashboard-panel` (vanaf `feature/hems-ev-module`), laatste commit `461631b`. Niet gepusht. `feature/hems-ev-module` is gepusht tot `c77ef10`. Niets is naar master gemerged.
- **Fase 0, opruimen:** klaar (Charge Amps, NetDaemon, ocpp-mirror weg). Restje: `update.netdaemon_update` staat alleen uit, en er staat nog een backup-tarball op de server.
- **Fase 1, prijzen naar HEMS:** gedaan. Rol `price_curve_entity` is weg. Open: de energy-prices-add-on stoppen (niet verwijderen) na een week meekijken, rond 3 nov.
- **Fase 2, dashboard:** eigen zijbalkpaneel `/hems`, rustig ontwerp met Today, Plan, Devices, Insights, een tandwiel en een kiosk. Plan in `docs/hems/dashboard-calm-plan.md`, ontwerp op https://claude.ai/artifact/GCQXjJawNXKxdmpSEQykij, werking in `docs/hems/dashboard.md`. Staat op de server; zichtbaar na een HA-herstart. Open: het oude dashboard `battery-management` en de BM-tegels vervangen.
- **EV-module:** gebouwd en aan, in dry-run. `docs/hems/ev-module-plan.md`.
- **Rollen:** `water_heater_entity` en `compare_action_entity` gezet. `legionella_last_entity` ontbreekt: de water-heater-add-on publiceert `sensor.wh_last_legionella` alleen bij een wijziging, dus na een HA-herstart is hij weg (bug in de add-on).
- **Fase 3–6** (SAJ-schrijflaag, advisory/auto, boiler en EV live, afbouwen): niet begonnen.

## Besluiten
- **Route B:** HEMS schrijft de SAJ H2-entiteiten zelf volgens het protocol van battery-api (live-transition-plan §4.2). Een watchdog buiten HEMS is verplicht. battery-api en battery-manager mogen niet tegelijk schrijven.
- **Legionella:** alleen op de legionelladag (kalenderdag), niet inhalen. HEMS neemt de add-on-regels over (§5.1).
- **Taal:** het paneel en de integratie zijn alleen Engels, er is geen `nl.json`.
- **Vensters:** een venster mag pauzes bevatten; `active_min` is de echte laad- of verkooptijd.

## Bewijs
- Core: 254 tests groen. Draai ze vanuit `hems/core` met `python -m pytest -q -p no:homeassistant -p no:pytest_homeassistant_custom_component`; zonder die vlaggen breekt de HA-plugin ze.
- HA: 62 tests groen (`python -m pytest tests/hems_ha -q`).
- Venv: `/mnt/work/Projects/Personal/ha-addons/.claude/venv/ha`, met plugin 0.13.373 (HA 2026.10.2). De server draait 2026.10.4; plugin 0.13.375 pint die versie.
- Engine-kopie: `python3 scripts/sync_hems_core.py --check`.

## Open
1. Na de HA-herstart in het echte paneel controleren:
   - de nieuwe indeling;
   - "Plan" in het Engels;
   - de "Active"-tijd;
   - de kiosk op de A9 (`/hems?kiosk`).
2. De water-heater-add-on moet `sensor.wh_last_legionella` opnieuw publiceren na een HA-herstart (eigen branch). Daarna de rol `legionella_last_entity` zetten.
3. Planner: verkopen met pauzes (16:30–19:30 met 3 rustkwartieren) kost straks extra SAJ-slots. Overweeg een regel voor een aaneengesloten blok, tenzij de pauze echt geld oplevert. Eerst meten wat het kost.
4. Insights: HEMS en de oude manager waren het in 4 van 50 kwartieren eens, en het resultaat was −€ 1,93 op de eerste dag. Uitzoeken waarom, nog zonder iets te veranderen.
5. Fase 2 afmaken: `battery-management` en de BM-tegels naar HEMS.
6. Fase 3: de SAJ-schrijflaag achter de modus, met een nepdienst in de tests, plus de watchdog en de test-plugin naar 0.13.375. Dit is vrijgave-gevoelig: onafhankelijke review en audit.
7. Rond 3 nov: de energy-prices-add-on stoppen.
8. Branches: `feature/hems-dashboard-panel` pushen en mergen (na mijn ja).

## Eerste stap
Lees `docs/hems/live-transition-plan.md` en `docs/hems/dashboard-calm-plan.md`, controleer `git status` en `git log origin/master..HEAD`, en vraag me welke van de open punten eerst moet. Mijn voorstel is punt 1, dan 2.

## Skills
`~/.agents/skills/ask-develop/SKILL.md`, `~/.agents/skills/ask-debugging/SKILL.md` (punt 4), `~/.agents/skills/ask-code-review/SKILL.md` (fase 3).
