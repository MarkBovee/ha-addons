# HEMS v2 — intake: besluiten en werklijst (2026-10-13)

Status van de plan-toets (ask-intake). Het Claude Doc "HEMS v2 — Plan" blijft het hoofdplan; waar dit bestand ervan afwijkt, geldt dit bestand tot het Doc is bijgewerkt. Afwijkingen zijn gemarkeerd met **WIJKT AF**.

## Destination
Een HEMS-kern (`hems/core`, geen HA-imports) die per kwartier een rolling-horizon plan maakt voor de batterij, geladen via een custom integration in dry-run. Eerst bewezen op replay van echte dagen (3-12 okt), pas daarna schrijfacties.

## Decisions so far
- **Runtime**: alleen custom integration (`custom_components/hems`, coordinator, config/options flow). Geen add-on, geen web-UI, geen tweede kanaal. `hems/core` blijft HA-vrij, zodat een add-on later kan. **WIJKT AF** van plan ("add-on draait logica, integratie publiceert").
- **Aansturing via HEMS-modules**: module `battery` stuurt op HA-entiteiten die de gebruiker aanwijst. Een module mag meerdere implementaties hebben (bv. generic en SAJ-specifiek). Vendor-kennis zit in adapters buiten `hems/core`; de kern en de contracten blijven vendor-vrij. battery-api blijft standalone bestaan en HEMS hangt er niet van af. **WIJKT AF** van brief ("geen saj_* in HEMS-code", "hardware-add-ons vertalen") en plan ("productkennis in aparte hardware-add-ons"). De MQTT-vraag vervalt voor HEMS.
- **Charge Amps/EV buiten beschouwing** tot nader order. Het EV-contract wacht; de balancer houdt een generieke EV-last.
- **SoC-vloeren, twee instellingen**: hard minimum 5% (absolute batterijlimiet, nooit lager) en reserve/conservatief 30% (instelling, later dynamisch op gebruik en temperatuur). Reserve >= hard minimum. De planner krijgt per slot een vloer (nu constant). Replay draait 5% en 30%.
- **Replay-prijzen**: kwartierhistorie van `sensor.current_price` uit de HA-recorder, via de collector, nu (detail verloopt na ~10 dagen). Markt = (import - 0,11085 - 0,02) / 1,21; export via `PriceModel`. Niet de state van `energy_prices_electricity_import_price` (ruwe marktprijs, bekende bug).
- **Marge**: `wear_cost` 0,10 komt bovenop het rendementsverlies (additief, zoals brief en code). De plantekst "rendement impliciet in de marge" wordt gecorrigeerd.
- **Round trip**: default 0,82 (gemeten over 3-12 okt: laden 220,5 kWh, ontladen 180,3 kWh, dSoC +1,3 kWh; in 7 uren met stilstaande batterij zakt de SoC mediaan 0 W, dus geen aanwijzing voor stand-by-verlies). Blijft een instelling; kalibreren in de replay. Vervangt de 0,90 uit plan en brief.
- **Zonnebonus = instellingen zoals energy-prices**: `export_vat_multiplier` 1,21, `export_bonus_pct` 0,10, `export_fixed_bonus` 0,02, `export_energy_tax` 0,11085, plus lengte- en breedtegraad (default uit HA). Actuele add-on-opties in HA gecontroleerd; ze komen overeen met de defaults in `prices.py`. Daarbovenop twee schakelaars, beide default aan: bonus alleen overdag (zonsopkomst-zonsondergang) en alleen bij positieve prijs. Reden: de README van energy-prices beschrijft dat gedrag en de Zonneplan-pagina bevestigt de positieve-prijs-eis voor de 10% (de vaste 0,02 geldt altijd). Het prijsmodel krijgt daarom een daglicht-vlag per slot. Replay draait met en zonder de schakelaars.
- **NetDaemon is archief**: geen NetDaemon-add-on geïnstalleerd (gecontroleerd in HA); de `input_boolean.netdaemon_*` helpers zijn restanten en geen HEMS-zaak. De batterij heeft daarmee twee sturende lagen (battery-manager en battery-api), niet drie.

## Besluiten tijdens de bouw (13 okt)
- **Prijsbron v1**: de `price_curve` van de energy-prices-sensor (aanwijsbare entiteit). Zelf Nord Pool ophalen blijft een vervolgstap uit het plan; de bron zit achter `import_curve` in `hems.dryrun`.
- **Open-Meteo bevestigd voor v1**: gratis, geen sleutel, kwartierdata; PV-factor gefit op 3-12 okt geeft R2 0,82. Alleen op 0,01° afgeronde coördinaten gaan de deur uit; uitzetbaar.
- **Alleen dry-run**: de integratie schrijft nooit naar een apparaat; `BatteryPort.apply` wordt in deze versie niet aangeroepen.
- **Engine als gegenereerde kopie**: `custom_components/hems/engine` komt uit `hems/core` via `scripts/sync_hems_core.py`; een test faalt als de kopie achterloopt.
- **Warm water (stap 4) en EV (Charge Amps) zijn niet gebouwd**; ze zijn niet nodig voor de eerste simulatie.
- **Replay-uitkomst** (4-11 okt, bekend verbruik en PV, 8 dagen, kasbasis): planner 16,84 EUR tegenover 15,37 EUR echt, met slijtagemarge 0,10; 22,03 EUR bij 0,05 en 24,49 EUR bij 0,00. Op 7-9 okt (dunne spreads) laadt de planner niet, waar de echte sturing verlies maakte. Zie `docs/hems/observations/replay-2026-10-13.md`.

## Open questions
1. Bonus op batterijstroom: Zonneplan beschrijft de bonus voor "zonnestroom"; of avondlevering uit de batterij hem krijgt en of hij incl. btw is, is onbevestigd. Controle op een echte afrekening; tot dan dekken de schakelaars en de replay beide gevallen.
2. Slijtagemarge: 0,10 EUR/kWh kost in de replay ongeveer 7,6 EUR over 8 dagen aan kasopbrengst ten opzichte van 0,00 (24,49 tegen 16,84). Wat is de echte afschrijving per ontladen kWh? Een LFP-accu van circa 5000 EUR bij 6000 cycli komt op ruwweg 0,04 EUR/kWh; dat is een aanname en geen meting.
3. Negatieve marktprijzen: de x1,10 maakt een negatieve prijs nog negatiever; opgelost zodra de positieve-prijs-schakelaar in het prijsmodel zit (test erbij).

## Not yet specified
- Dynamisch reservebeleid (gebruik, temperatuur).
- Hoe de config flow een module-implementatie kiest en entiteiten per capability toewijst.
- Warm-water-contract (stap 4) en EV-contract (na Charge Amps).
- Offset huisverbruik: P1 + `saj_total_grid_power` ligt gemiddeld +329 W boven `saj_total_load_power`; kalibreren in stap 6.

## Out of scope
- Charge Amps/EV-planner en evcc-onderzoek (tot nader order).
- Add-on-runtime en web-UI voor HEMS.
- Ombouw van battery-api (MQTT weghalen); `openspec/` (per instructie).
- NetDaemon: archief, niets meer mee te doen voor HEMS.

## Werklijst

**Must**
1. Prijsfixtures 3-12 okt uit de recorder (tijdkritisch: 6 okt valt rond 16 okt weg). Collector bewaart voortaan de volledige curve.
2. Balancer: niet-stuurbare lasten eerst aftrekken. Nu geeft huis 7000 + batterij 8000 + warmtepomp 5000 een totaal van 20 kW bij een limiet van 15 kW. Test erbij.
3. Forecast: kwartier-offset (`to_slots_kwh` neemt alleen `start_hour`), datetime-sleutels in plaats van rijtelling, UTC-tijdlijn. DST eindigt 25 okt, een dag van 25 uur.
4. Planner: vloer per slot (hard minimum en reserve).
4b. Prijsmodel: daglicht-vlag per slot, schakelaars voor bonus alleen overdag en alleen bij positieve prijs, tests op negatieve prijzen. Let op: de code van energy-prices past de bonus altijd toe (daglicht wordt berekend maar niet gebruikt, README zegt het tegendeel). De export-sensor en de rendementsschattingen in het plan zijn daardoor voor avondverkoop te hoog (de 10%-component is circa 0,036 EUR/kWh bij 0,30 marktprijs); herberekenen in de replay.
5. Stap 1 omvat batterij, grid, prijzen en huisverbruik, met fakes. Warm water volgt in stap 4, EV later.
6. Replay-acceptatie (stap 2): planner-saving >= 0, geen cyclus met spread kleiner dan slijtage plus verlies, op 6 okt, het paar 7+8 okt en 9 okt. De 7 okt-nachtlading wordt door de DP geweigerd (per opgeslagen kWh: verkopen 0,304 tegenover laden 0,348); de replay toetst economie en bootst battery-manager niet na.

**Should**
- DP levert de marginale waarde van opgeslagen energie per slot, zodat de trace redenen kan geven ("waarom niet verkopen?"). Klok injecteren in `trace.record`, rotatie toevoegen.
- Plantekst corrigeren: marge, add-on+web-UI, "MQTT vervalt", rol van battery-api.

**Could**
- PV-curtailment bij negatieve prijzen, bewaking per fase, Predbat (batterijdeel) doorlezen.

## Test-naden
1. Publieke kern-API (`plan`, `allocate`, prijs- en forecastfuncties) met echte-prijs-fixtures.
2. Contractgrens met fake-implementaties (stap 1).
