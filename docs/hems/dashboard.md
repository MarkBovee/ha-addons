# HEMS-dashboard (paneel)

HEMS registreert zelf een paneel **HEMS** in de zijbalk (`/hems`). Het paneel zit in de integratie (`custom_components/hems/frontend/hems-panel.js`) en wordt met `hems/deploy.py` meegeleverd. Er is geen HACS-kaart en geen build-stap nodig.

## Data
- `hems/subscribe` (websocket): de hele horizon per kwartier, de beslissing met de vergelijking (verkoop/bewaar/koop), de executor, vensters, boiler, EV en de plan-diff. HEMS pusht na elke cyclus, elke SoC-hercontrole en elke wijziging van de override. Dit wordt niet in de recorder opgeslagen.
- `hems/settings` (websocket): de opties in gebruik, de entiteitrollen en het entry-id.
- Live vermogens komen rechtstreeks van de entiteiten in de rollen.
- Nieuwe sensoren: `sensor.hems_plan_diff` (gewijzigde kwartieren sinds het vorige plan) en `sensor.hems_last_cycle`.

## Views
`#nu`, `#plan`, `#prijzen`, `#batterij`, `#auto`, `#boiler`, `#net`, `#regie`.

## Wandtablet (Galaxy Tab A9)
Open `/hems?kiosk#nu` in de companion app. `?kiosk` verbergt de kop, toont onderaan grote tabs en zet het thema altijd op donker. Zet in de companion app de zijbalk uit en houd het scherm aan tijdens het laden.

## Lovelace-kaarten
Het paneel laadt ook twee kaarten op elk dashboard:
```yaml
type: custom:hems-timeline-card
hours: 24          # 8, 24 of 48
title: Plan
lanes: [price, plan, soc, pvload, devices]
---
type: custom:hems-verdict-card
chain: true
```

## Resultaat en leren
HEMS meet elke 10 s net, zon en batterij en prijst per kwartier (`sensor.hems_cost_today`). Tegelijk rekent het dezelfde zon en hetzelfde huis door met een batterij op alleen zelfverbruik (`sensor.hems_realised_vs_baseline_today`, `sensor.hems_realised_total`). Per kwartier bewaart het ook de eigen verwachting. Daaruit komen `sensor.hems_pv_forecast_error` en `sensor.hems_load_forecast_error` (MAE en bias in kWh/dag) en de P10–P90-banden in de tijdlijn. Die banden staan op een standaardwaarde tot er 96 bruikbare kwartieren zijn. De metingen staan in `.storage/hems.<entry_id>`; de laatste 8 dagen worden bewaard.

Wijs bij **Reconfigure** optioneel nog drie entiteiten toe:
- `water_heater_entity`: de boiler of de tanktemperatuur
- `legionella_last_entity`: tijdstip van de laatste legionella-run
- `compare_action_entity`: de actiesensor van de oude battery manager, voor de vergelijking per kwartier in **Leren**

## Sturen en advies
- `switch.hems_master_arm`: de hoofdschakelaar. Na elke herstart staat hij uit. Er schrijft nog geen module, dus wapenen verandert nu niets; het wordt wel gelogd.
- `select.hems_{battery,ev,water_heater}_mode`: `dry_run` of `advisory`. `auto` komt pas met de eerste module die zelf stuurt.
- `sensor.hems_recommendations`: open adviezen. Een genegeerd advies komt terug als het plan iets anders vraagt.
- Services:
  - `hems.apply_recommendation` met `id`: vuurt `hems_recommendation_applied` af met module, actie, van/tot en vermogen of stroom. Jouw automatisering voert het uit, zodat HEMS niets rechtstreeks aanstuurt.
  - `hems.dismiss_recommendation` met `id`
  - `hems.disarm_all`

Voorbeeld voor de laadpaal:
```yaml
triggers:
  - trigger: event
    event_type: hems_recommendation_applied
    event_data: {module: ev}
actions:
  - action: number.set_value
    target: {entity_id: number.ocpp_hub_ed13009a_charge_limit}
    data: {value: "{{ trigger.event.data.current_a }}"}
```

## Meldingen
- `binary_sensor.hems_alert_data`, `_deadline`, `_not_executed` en `_legionella`, met de reden als attribuut.
- Blueprint `blueprints/automation/hems/hems_notify.yaml`: kopieer hem naar `/config/blueprints/automation/hems/` of importeer hem via de GitHub-URL.
- Stil tussen 22:00 en 08:00. Valt een melding in die uren, dan gaat hij om 08:00 alsnog uit als het alarm nog aan staat.
- "Plan niet uitgevoerd" gaat bij een gewapende HEMS altijd direct door.
- Ook "HEMS draait niet" (laatste cyclus ouder dan 30 min) geeft een melding.
