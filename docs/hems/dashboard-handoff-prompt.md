# Prompt voor Claude Code: HEMS-dashboard verder brengen

Kopieer alles onder de streep als eerste bericht in een nieuwe Claude Code-sessie in deze repo, op branch `feature/hems-dashboard-panel`.

---

Je gaat verder met het HEMS-dashboard: een eigen zijbalkpaneel van de HEMS-integratie (`custom_components/hems`) in Home Assistant 2026.10. Antwoord in het Nederlands, kort en technisch precies. Push en deploy niet zonder mijn akkoord.

## Stand van zaken
Branch `feature/hems-dashboard-panel` (vanaf `feature/hems-ev-module`) heeft twee commits, niet gepusht en niet gedeployed:
- `3afa3d6`: paneel, websocket-feed, plan-diff, last-cycle.
- `a85b5a3`: gerealiseerd resultaat, foutmaat en banden, modi, advies, alarmen, blueprint, Leren-view.

62 tests slagen tegen HA 2026.10.2 (`pytest-homeassistant-custom-component==0.13.373`, Python 3.14). Twee reviews zonder P0/P1. De bekende P2-punten staan hieronder.

## Lees eerst
1. `docs/hems/dashboard-design-prompt.md`: mijn oorspronkelijke brief, met alle wensen.
2. Het ontwerp (concept, visueel systeem, schermen, bouwspec): https://claude.ai/artifact/EsELinu5SQ3uhfKrBbSBDT
3. `docs/hems/dashboard.md`: hoe het nu werkt (entiteiten, services, kiosk, kaarten, blueprint).
4. `AGENTS.md`: HA is de enige integratiegrens; HEMS kent geen merk of protocol.

## Architectuur zoals gebouwd
- **`panel.py`**
  - Registreert paneel `/hems` (`panel_custom`, web component `hems-panel`) en serveert `frontend/` op `/hems_static`.
  - Laadt dezelfde module via `add_extra_js_url`, zodat de Lovelace-kaarten `custom:hems-timeline-card` en `custom:hems-verdict-card` overal bestaan.
  - Cache-buster is de mtime van het JS-bestand.
  - Zonder frontend (tests) wordt de registratie overgeslagen.
- **`frontend/hems-panel.js`**
  - Eén ES-module zonder dependencies en zonder build-stap, vanilla web components en SVG. Ik wilde geen Lit of Vite.
  - Views via de hash: `#nu`, `#plan`, `#prijzen`, `#batterij`, `#auto`, `#boiler`, `#net`, `#leren`, `#regie`.
  - URL-opties `?kiosk` (wandtablet Galaxy Tab A9, altijd donker) en `?theme=dark|light`.
- **`websocket.py`**
  - `hems/subscribe` pusht de payload via dispatcher-signaal `hems_dashboard_update` na elke coordinator-update.
  - `hems/settings` geeft opties, rollen en entry-id.
  - Commands en services worden één keer geregistreerd in `async_setup`.
- **`dashboard.py`**: `build_payload()` met `meta`, `battery`, `execution`, `decision`, `quarters[]` (hele horizon: prijs, actie, vermogen, SoC, reden, verkoop/koop/bewaar, PV/load met P10–P90, EV-stroom, boiler), `windows`, `sell_windows`, `heating`, `ev` en `diff`. Daarnaast `plan_diff()`.
- **`coordinator.dashboard_payload()`** voegt `control`, `alerts` en `realised` toe. Het resultaat wordt gecachet op het snapshot-object, bewust niet op `id()`.
- **`realised.py`** (`Ledger`, puur)
  - Integreert grid, PV, batterij en EV elke 10 s per kwartier (`SAMPLE_SECONDS`). Gaten boven 120 s tellen niet mee.
  - Prijst elk kwartier met de prijs en verwachting die HEMS had (`_remember_quarters`).
  - Baseline: batterij alleen op zelfverbruik, op het hele huis inclusief de auto. De gemeten base load is exclusief de auto, net als de verwachting.
  - Kwartieren met minder dan 60 % dekking tellen niet mee in totalen en foutmaten.
  - Verder: dagtotalen, foutmaat (MAE en bias, 7 d) en banden. Standaardbanden tot 96 kwartieren.
  - Opslag in `.storage/hems.<entry_id>`, samen met `Control`.
- **`advice.py`** (`Control`, puur)
  - Modi `dry_run` en `advisory` per module (`battery`, `ev`, `water_heater`). `auto` heb ik bewust niet aangeboden, omdat nog geen module schrijft.
  - `armed` wordt nooit opgeslagen.
  - Het advies-id is een hash van module, kind, action, to, power_w en current_a. Een genegeerd advies komt dus terug als het plan dat verandert.
- **Services**
  - `hems.apply_recommendation`: alleen voor open adviezen; vuurt het event `hems_recommendation_applied` af. HEMS schrijft zelf naar geen enkel apparaat.
  - `hems.dismiss_recommendation`.
  - `hems.disarm_all`.
- **Nieuwe entiteiten**
  - Sensoren: `sensor.hems_{plan_diff, last_cycle, cost_today, realised_vs_baseline_today, realised_total, pv_forecast_error, load_forecast_error, recommendations}`.
  - Selects: `select.hems_{battery,ev,water_heater}_mode`.
  - Switch: `switch.hems_master_arm`.
  - Alarmen: `binary_sensor.hems_alert_{data,deadline,not_executed,legionella}`.
  - Entiteitsnamen blijven Engels in elke taal; een test controleert dat.
- **Nieuwe optionele rollen** (Reconfigure): `water_heater_entity`, `legionella_last_entity`, `compare_action_entity` (oude battery manager, voor Leren).
- **Blueprint** `blueprints/automation/hems/hems_notify.yaml`: companion-app-meldingen, stil van 22:00 tot 08:00, "niet uitgevoerd" direct als gewapend, en een melding als HEMS niet meer draait (`sensor.hems_last_cycle`).

## Werkwijze en valkuilen
- **Worktree:** `.claude/worktrees/hems`. Het `.git`-bestand wijst naar een hostpad. Werk je vanuit een andere mount, gebruik dan `git --git-dir=.git/worktrees/hems --work-tree=.claude/worktrees/hems`.
- **Tests:** `python -m pytest tests/hems_ha -q`, in een venv met Python 3.14 en `pytest-homeassistant-custom-component==0.13.373`.
  - De testtijdzone is US/Pacific en de klok staat bevroren. Een echte websocket-client faalt dan op auth; gebruik de `FakeConnection` in de tests.
  - Callbacks van `async_track_time_interval` moeten `@callback` zijn.
- **Bekende fout in de core:** `hems/core`-test `test_vendored_engine_matches_the_core` faalde al vóór deze branch. Uitzoeken.
- **Engine-kopie:** raak de engine (`custom_components/hems/engine` = `hems/core/hems`) alleen aan als je beide kopieën synchroon houdt.
- **Paneel visueel checken:** een harness met een nep-`hass` en een payload uit een test-dump, met Playwright-screenshots op 390, 893 (A9) en 1180 px.

## Open: eerst doen
1. Deploy (`python3 hems/deploy.py --restart`, na mijn akkoord). Controleer in de echte HA:
   - verschijnt het paneel en vult de payload zich;
   - geen fouten in de browserconsole of het HA-log;
   - de live-tegels gebruiken de juiste rollen;
   - werkt het op de A9 (`/hems?kiosk#nu`, zijbalk uit).
2. Rollen invullen en controleren:
   - `water_heater_entity`
   - `legionella_last_entity` (`sensor.wh_last_legionella`)
   - `compare_action_entity` (`sensor.battery_manager_current_action`; check welke statewaarden die sensor geeft, want `norm()` in `_view_leren` herkent laden en ontladen op tekst).
3. Blueprint end-to-end testen: importeren, telefoon kiezen, een alarm forceren, de stille uren controleren.

## Open: P2-punten uit de reviews
- **Baseline-SoC na een HA-storing:** de gemiste kwartieren worden niet gesimuleerd. Overweeg het opnieuw ankeren op de echte SoC na een gat van meer dan een uur.
- **Sensoren voor "vandaag"** tonen tot het eerste kwartier na middernacht nog gisteren. Rol de dag ook op de klok, niet alleen bij het sluiten van een kwartier.
- **Hold-to-arm** heeft geen toetsenbordpad.
- **Blueprint-queue:** `mode: queued`, max 10. Adviezen die in de stille uren wachten, houden de queue bezet.
- **Reden-zinnen** komen in het Engels uit de engine (bijvoorbeeld "sell 0.444 > keep 0.404"). Vertaal ze in het paneel of laat de engine gestructureerde codes leveren.
- **Paneelregistratie** (`panel.py`) wordt in de tests niet doorlopen. Voeg een test toe met de frontend-component, of een mock.

## Open: functioneel, uit mijn brief
- **Notificatie bij een advies** (advisory), met actieknoppen Toepassen en Negeren in de companion app (`mobile_app` actionable notifications naar `hems.apply_recommendation`).
- **Leren:**
  - "Leg de uitkomst van een willekeurige dag uit": klik op een dag in het resultaat per dag en open die dag in de tijdlijn met de gemeten kwartieren.
  - "Beslissingen die achteraf goed of fout bleken": vergelijk geplande en gerealiseerde prijs per venster.
- **Net:** geschiedenis van begrenzingen door de load balancer (HEMS publiceert die nog niet) en "wie gebruikt wat" per fase.
- **Batterij:** voorraadkostprijs (gemiddelde inkoopprijs van wat erin zit) en cycli per dag. Beide zijn nieuwe sensoren uit de ledger.
- **Prijzen:** het effect van het einde van de saldering visueel tonen (exportprijs vóór en na 2027-01-01).
- **Live-overgang:** de eerste module met een echte schrijver (waarschijnlijk de laadpaal). Pas dan `auto` als modus toevoegen, met bevestiging en een zichtbaar gewapende staat. `writers` in `payload.control` is daarvoor al gereserveerd.

Begin met punt 1 van "Open: eerst doen": rapporteer wat je ziet en stel per bevinding een fix voor.
