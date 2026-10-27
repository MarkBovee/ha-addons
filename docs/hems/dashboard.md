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

## Nog niet (volgt met HEMS-uitbreidingen)
- gerealiseerd resultaat t.o.v. zelfverbruik
- P10–P90-banden op de verwachtingen
- hoofdschakelaar, modi en advies (Toepassen/Negeren)
- meldingen
- vergelijking met de oude battery manager
- geschiedenis/Leren
