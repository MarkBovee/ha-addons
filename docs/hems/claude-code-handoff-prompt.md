# Prompt voor Claude Code: HEMS v2 verder bouwen

Kopieer alles onder de streep als eerste bericht in een nieuwe Claude Code-sessie in deze repo (branch `feature/hems-observations`, of een nieuwe branch daarvan).

---

Je bouwt HEMS v2 verder: een modulair, hardware-agnostisch home energy management systeem voor Home Assistant (custom integration + add-on, Python). Antwoord in het Nederlands, kort en technisch precies. Negeer `openspec/`. Push niet zonder mijn akkoord.

## Lees eerst
1. Het plan: Claude Doc "HEMS v2 — Plan" (https://claude.ai/code/artifact/8939c11e-355c-4baf-af6e-21032215ae21), bron van waarheid voor besluiten.
2. `hems/core/README.md` en `hems/core/hems/*.py` (bestaande kern, 7 tests groen: `cd hems/core && pytest`).
3. `docs/hems/observations/log.md` (analyse van de data 3-12 okt) en `docs/hems/battery-manager-fix-prompt.md` (loopt in een andere sessie; niet aanpassen).
4. `scripts/hems_collect.py` en `docs/hems/observations/data/*.jsonl` (lokaal, gitignored: hourly, snapshots, plans) voor echte data.

## Harde ontwerpregels
- HEMS kent GEEN hardware. Alleen generieke capability-contracten: batterij, EV-lader, warm water, grid, prijzen. SAJ (battery-api) en Charge Amps blijven eigen hardware-add-ons die het contract aanbieden en generieke commando's (watt, moment) vertalen naar slots/percentages. Geen `saj_*` of Charge Amps-namen in HEMS-code.
- `hems/core` blijft vrij van Home Assistant-imports; HA-specifiek zit in een aparte laag (coordinator, sensoren, config flow).
- Kwartier is de tijdeenheid. Rolling horizon. Verkoopuren worden bepaald over de cyclus laden -> ontladen, niet per kalenderdag (DP in `battery.py` doet dit al).
- Vaste marge (`wear_cost` 0,10 EUR/kWh ontladen) plus rendement (round trip 0,90). SoC-vloer 30% (nog te bevestigen).
- Prijzen: import = markt*1,21+0,11085+0,02; export 2026 (saldering) = markt*1,10*1,21+0,02+0,11085; export 2027 = markt*1,10+0,02; instelling "Salderen ja/nee".
- Load balancer: standaard netlimiet 15.000 W (configureerbaar), prioriteiten, hysterese.
- Verbruiksvoorspelling = algoritme op historie van de laatste X dagen + weer + PV-voorspelling. Weer/zon via externe API (voorstel Open-Meteo, nog bevestigen), door HEMS als eigen sensoren aangeboden.
- Elke beslissing krijgt een regel in een decision trace (JSONL) zodat "waarom laden/niet verkopen?" achteraf te beantwoorden is.
- Huisverbruik = `sensor.power_usage` (P1, negatief = export) + `sensor.saj_total_grid_power`, min EV-vermogen. In HEMS achter een generiek "huisverbruik"-contract zetten; `battery_api_load_power` is onbetrouwbaar.

## Wat er staat
`hems/core`: `prices.py`, `battery.py` (DP-planner), `balancer.py`, `forecast.py` (mediaan per uur), `trace.py`, tests. Prior art: HAEO, EMHASS, BatteryLabs 3-Phase (zie plan, sectie "Bestaande projecten"); evcc en Predbat nog niet bekeken.

## Volgende stappen (in deze volgorde, klein en getest)
1. Contracten: dataclasses/Protocols voor batterij, EV, warm water, grid, prijzen (commando's, status, versheid, eenheden) in `hems/core`, met fake-implementaties voor tests.
2. Replay-test: laad `hourly.jsonl`/prijzen van 6, 7 en 9 okt en toets de planner aan de uitkomsten in `log.md` (7 okt: nachtlading rendeerde op 8 okt; 9 okt dunne spread, weinig rendement). Gebruik de echte kwartierprijzen waar beschikbaar.
3. Rolling-horizon wrapper: elk kwartier herplannen met actuele SoC, PV- en verbruiksvoorspelling; schrijf trace.
4. Warm water: planner voor de warmtepomp-boiler (eenmaal per dag DHW, legionellacyclus bijhouden in HEMS; tanksensor max 59 °C dus offset-probleem, zie plan).
5. HA-laag: custom integration (`custom_components/hems`), coordinator, sensoren, config flow, entiteiten die de gebruiker aanwijst per capability.
6. Verbruiksvoorspelling v1 (mediaan/regressie op 7 dagen) en Open-Meteo-sensoren.
7. Evcc en Predbat doorlezen voor EV-laadstrategie en wat we kunnen hergebruiken; noteer in het plan.

## Werkwijze
- Kleine commits, conventional commits, tests bij elk gedrag. Draai `pytest` voor elke commit.
- Werk het plan bij (Claude Doc) of schrijf besluiten in `docs/hems/` als je ervan afwijkt, en zeg dat expliciet.
- Vraag bij echte keuzes die het plan niet beantwoordt (SoC-vloer, Zonneplan-bonus, NetDaemon uitzetten); verzin geen aannames over hardware.
