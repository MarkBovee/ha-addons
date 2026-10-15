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
- **Marge**: geen slijtagemarge maar een **minimale winstmarge** (`min_profit_margin`, standaard 0,10 EUR per ontladen kWh, bovenop het rendementsverlies). Het is een drempel voor de planner en nooit een kostenpost: de replay en de verwachte besparing zijn kas. (Besluit Mark, 13 okt; vervangt `wear_cost`.) De plantekst "rendement impliciet in de marge" wordt gecorrigeerd.
- **Round trip**: default 0,82 (gemeten over 3-12 okt: laden 220,5 kWh, ontladen 180,3 kWh, dSoC +1,3 kWh; in 7 uren met stilstaande batterij zakt de SoC mediaan 0 W, dus geen aanwijzing voor stand-by-verlies). Blijft een instelling; kalibreren in de replay. Vervangt de 0,90 uit plan en brief.
- **Zonnebonus = instellingen zoals energy-prices**: `export_vat_multiplier` 1,21, `export_bonus_pct` 0,10, `export_fixed_bonus` 0,02, `export_energy_tax` 0,11085, plus lengte- en breedtegraad (default uit HA). Actuele add-on-opties in HA gecontroleerd; ze komen overeen met de defaults in `prices.py`. Daarbovenop twee schakelaars, beide default aan: bonus alleen overdag (zonsopkomst-zonsondergang) en alleen bij positieve prijs. Reden: de README van energy-prices beschrijft dat gedrag en de Zonneplan-pagina bevestigt de positieve-prijs-eis voor de 10% (de vaste 0,02 geldt altijd). Het prijsmodel krijgt daarom een daglicht-vlag per slot. Replay draait met en zonder de schakelaars.
- **NetDaemon is archief**: geen NetDaemon-add-on geïnstalleerd (gecontroleerd in HA); de `input_boolean.netdaemon_*` helpers zijn restanten en geen HEMS-zaak. De batterij heeft daarmee twee sturende lagen (battery-manager en battery-api), niet drie.

## Besluiten tijdens de bouw (13 okt)
- **Prijsbron**: HEMS haalt Nord Pool day-ahead zelf op (kernmodule `hems.nordpool`, besluit Mark 13 okt); gevalideerd tegen een echte dag (96 van 96 kwartieren gelijk aan de opgenomen consumentenprijzen, verschil <= 0,00015 door afronding in de add-on). De `price_curve`-sensor is optionele terugval en controle. `binary_sensor.hems_tomorrow_prices_available` meldt of morgen bekend is.
- **Open-Meteo blijft** (besluit Mark 13 okt): gratis, geen sleutel, kwartierdata; PV-factor gefit op 3-12 okt geeft R2 0,82. Alleen op 0,01° afgeronde coördinaten gaan de deur uit; uitzetbaar.
- **Alleen dry-run**: de integratie schrijft nooit naar een apparaat; `BatteryPort.apply` wordt in deze versie niet aangeroepen.
- **Engine als gegenereerde kopie**: `custom_components/hems/engine` komt uit `hems/core` via `scripts/sync_hems_core.py`; een test faalt als de kopie achterloopt.
- **Warm water (stap 4) en EV (Charge Amps) zijn niet gebouwd**; ze zijn niet nodig voor de eerste simulatie.
- **Replay-uitkomst** (4-11 okt, bekend verbruik en PV, 8 dagen, kasbasis): planner 16,76 EUR (zonder wachtkosten; met standaard wachtkosten 0,002: 18,15 EUR) tegenover 15,37 EUR echt, met minimale winstmarge 0,10; 21,97 EUR bij 0,05 en 24,49 EUR bij 0,00 (kas). Op 7-9 okt (dunne spreads) laadt de planner niet, waar de echte sturing verlies maakte. Zie `docs/hems/observations/replay-2026-10-13.md`.

- **Logging in drie lagen** (besluit Mark 13 okt: alle beslissingen en de hele plan-boom kunnen volgen): `decision_trace.jsonl` (beslissing, invoer, vergelijking, segmenten), `plans.jsonl` (elk geplande kwartier met invoer), `events.jsonl` (ophalen, statuswissels, instellingen); lezen met `scripts/hems_trace.py`. Gevonden tijdens het bouwen: de planner begrensde het vermogen aan de accu-kant, waardoor laden op 8,8 kW AC kon uitkomen bij een omvormer van 8 kW; nu AC-begrensd (replay-cijfers hieronder zijn daarmee opnieuw berekend).
- **Planner en uitvoerder gescheiden** (opmerking Mark 13 okt: de planner moet zorgen dat de SoC geladen is vóór het verkopen, de uitvoerder checkt de SoC vóór de echte actie): de planner deed het eerste al (de DP laat laden onder de reserve toe en verkoopt pas uit de geladen energie; vastgelegd in een test met start op 24 %). Nieuw is `executor.py`: controleert elke opdracht tegen de actuele SoC bij elke SoC-update, houdt een ontlading vast op de vloer, vertraagt tot wat er boven de vloer over is, weigert laden bij vol, houdt vast bij ontbrekende of oude SoC en bij een verlopen plan. Zodra HEMS naar de batterij schrijft, gaat dat uitsluitend via de uitvoerder.
- **Wachtkosten** (zorg Mark 13 okt: bijna 16 uur tussen laden en ontladen): vasthouden was gratis in de planner, dus bij gelijke prijzen laadde hij zo vroeg mogelijk. Stilstandsverlies is gemeten klein (ca. 0,1 % SoC per uur), het risico zit in onzekerheid en beslisruimte. Instelling `hold_cost_kwh_h`, standaard 0,002 EUR per kWh per uur (0 = uit). Mark zet battery-manager parallel op sell buffer 4 uur vóór de verkoop en 40 % (13 okt), dus HEMS laadt ook laat. Replay 4-11 okt, kas: uit 16,76; 0,001 16,94; 0,002 18,15; 0,003 17,98; 0,005 17,25; 0,008 14,33. Gemengd per dag: 6 okt (grootste spread) verliest € 1,24, de rest wint. De monitoring beoordeelt of 0,002 blijft staan.
- **Tijden met dag** (opmerking Mark 13 okt): 07:30 in een plan van 48 uur is morgen; logs en leestool tonen `+1d`.
- **Zichtbaar in het HA-log**: de server staat op `logger: default: warning`; de integratie zet zijn eigen logger bij het starten op INFO (tenzij de gebruiker er een niveau voor instelde). Per kwartier een beslisregel en de plan-boom, elk event als regel, overschrijving door de uitvoerder en status ongelijk aan ok als WARNING.
- **Monitoring** (besluit Mark 13 okt): geplande taak `hems-dry-run-monitoring`, dagelijks 08:26, read-only; rapporten in `docs/hems/observations/monitoring/`; weekoverzicht na 20 okt.
- **Lessen uit het battery-manager-incident van 14 okt** (de ochtendpiek 07:30-09:30, export tot 0,62, werd gemist omdat sinds 0.8.87 alleen kwartieren na het hoofdlaadvenster verkocht mochten worden; opgelost in battery-manager 0.9.0):
  1. *Een heuristiek die kandidaten stilletjes weghaalt is de foutklasse.* HEMS houdt één economisch doel over de hele horizon (DP): geen uurbudgetten, geen vaste prijsplafonds, geen "alleen na het laadvenster". Elke beperking is een geprijsde term (marge, wachtkosten, vloer) en verschijnt in het spoor met haar reden. Test: `hems/core/tests/test_two_peaks.py` plant de echte dag van 14 okt en eist beide pieken, nachtlading vooraf, middaglading op de dan actuele SoC en het verkopen van het duurste kwartier.
  2. *De uitleg moet bij de beslissing passen.* Bij het nalezen bleek de uitleg van HEMS in 70 van 258 verkoopkwartieren (27 %) te beweren "sell > keep" met cijfers die dat tegenspraken: een ontlading boven het huisverbruik werd tegen de importprijs gewaardeerd terwijl het kWh op de exportprijs landt. De beslissing was goed, de uitleg niet. Nu geprijsd waar het kWh landt, en waar de marginale vergelijking de keuze niet bevestigt (de waardefunctie is niet convex door de winstmarge) staat er "plan-level" in plaats van een valse ongelijkheid. Test op negen opgenomen dagen.
  3. *Dekking van pieken is een monitoringvraag*, niet alleen een gezondheidsvraag: de dagelijkse review controleert nu per prijsblok of HEMS en de echte batterij verkopen, en schrijft een gemiste, winstgevende piek op als bevinding.
  4. *Voorladen hoort bij de wachtkosten, niet bij een uur-instelling.* battery-manager's `sell_buffer_activation_hours_before_sell` en HEMS' `hold_cost_kwh_h` lossen hetzelfde op (niet te vroeg laden); de vaste activatietijd laadt tegen de prijs van dat moment (0,33 in plaats van 0,27 om 00:00), de wachtkosten wegen dat af.
  5. *Dry-run kan niet bewijzen wat de uitvoering waarmaakt.* HEMS adviseerde om 04:00 en 05:00 te laden, maar zonder aansturing bleef de SoC 55-58 %, dus het ochtendadvies draaide vanaf 51 % in plaats van 62 %. De review vergelijkt daarom beslissingen per kwartier met de echte prijzen, niet SoC met SoC.
  6. *Werkwijze:* reproduceer het incident eerst met de echte prijzen van die dag (fixture), toon de oorzaak in het spoor, repareer, en draai een dagsimulatie kwartier voor kwartier; versie ophogen bij elke wijziging aan een add-on.
  7. *Een verkoopvenster is een analyse van de prijzen en het plan, geen filter ervoor* (besluit 15 okt 2026, na de vraag om een detectiemechanisme waarop alle keuzes rusten). Proef op elf echte dagen, elk vanaf 30 % en 83 % SoC, planner beperkt tot door prijzen gedetecteerde vensters: zonder voorraad (30 %) kost het €0,00, met voorraad (83 %) €13,97 van €105 als het venster alleen naar een laadmoment ervóór kijkt en €1,48 als het ook naar het terugkopen erna kijkt (de enige grote post is het einde van een horizon van één dag). De reden: dezelfde piek is wel een venster met voorraad en niet zonder (15 okt, 08:00: met voorraad weer vullen op 0,23 om 14:00, zonder voorraad een nachtlading op 0,332 die de drempel van 0,514 niet haalt, de piek haalt 0,489). Alleen het plan kent de SoC. Daarom is `hems/core/hems/windows.py` alleen-lezen: het detecteert vensters (drempel = importprijs / 0,82 + marge + wachtkosten, op twee grondslagen: vers laden ervoor of terugkopen erna), wijst elke lading toe aan de verkoop waarvoor hij dient (oudste energie eerst) en controleert het plan (`planned`, `partial`, `no_stock`, `kept_for_later`, `unsold`, en kWh buiten elk venster). Het beslist niets. Op de opgenomen dagen ligt over 48 uur elke geplande verkoop binnen een venster (test); over één dag niet (de eindwaarde van de horizon laat voorraad dumpen).


## Open questions
1. Bonus op batterijstroom: Zonneplan beschrijft de bonus voor "zonnestroom"; of avondlevering uit de batterij hem krijgt en of hij incl. btw is, is onbevestigd. Controle op een echte afrekening; tot dan dekken de schakelaars en de replay beide gevallen.
2. Negatieve marktprijzen: de x1,10 maakt een negatieve prijs nog negatiever; opgelost zodra de positieve-prijs-schakelaar in het prijsmodel zit (test erbij).

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
6. Replay-acceptatie (stap 2): planner-saving >= 0, geen cyclus met spread kleiner dan minimale winstmarge plus verlies, op 6 okt, het paar 7+8 okt en 9 okt. De 7 okt-nachtlading wordt door de DP geweigerd (per opgeslagen kWh: verkopen 0,304 tegenover laden 0,348); de replay toetst economie en bootst battery-manager niet na.

**Should**
- DP levert de marginale waarde van opgeslagen energie per slot, zodat de trace redenen kan geven ("waarom niet verkopen?"). Klok injecteren in `trace.record`, rotatie toevoegen.
- Plantekst corrigeren: marge, add-on+web-UI, "MQTT vervalt", rol van battery-api.

**Could**
- PV-curtailment bij negatieve prijzen, bewaking per fase, Predbat (batterijdeel) doorlezen.

## Test-naden
1. Publieke kern-API (`plan`, `allocate`, prijs- en forecastfuncties) met echte-prijs-fixtures.
2. Contractgrens met fake-implementaties (stap 1).
