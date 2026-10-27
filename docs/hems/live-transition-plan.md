# Van dry-run naar live: scan van de HA-server en plan (27 okt 2026)

Status: **analyse en plan, niets gebouwd, niets gewijzigd.** Alles hieronder komt uit leesacties op de server (HA MCP en REST, 27 okt 2026 08:00 tot 08:40) en uit de repo. Wat ik niet kon controleren staat in hoofdstuk 8. Er zijn geen opties van battery-manager gelezen of gekopieerd. Bij het lezen van de water-heater-add-on kwamen de MQTT-gegevens van die add-on in plaats mee in het antwoord; ik heb ze nergens opgeslagen.

## 1. Samenvatting

1. **HEMS kan nu niets besturen.** Er is geen schrijflaag, geen modus per module (dry-run, advisory, auto) en geen hoofdschakelaar. "Dry-run weghalen" is dus geen schakelaar omzetten maar een nieuwe laag bouwen, per apparaat.
2. **De lader en de batterij zijn verschillende gevallen.** Voor de batterij moet een bestaande besturing (battery-manager via battery-api) worden afgelost. Voor de EV is HEMS de eerste en enige besturing, met een stroomproef als voorwaarde.
3. **Beslist (Mark, 27 okt): route B, HEMS schrijft de SAJ-entiteiten direct.** Battery API krijgt zijn schema alleen via een MQTT-topic en HEMS mag geen MQTT gebruiken; de SAJ-integratie biedt wel native HA-entiteiten (tijdsloten, passieve besturing). HEMS bouwt dus zelf de SAJ-uitvoerder, met hetzelfde schrijfprotocol als de Modbus-backend van battery-api (hoofdstuk 4). Eén correctie op eerdere aannames: de tijdsloten zijn **dagelijks terugkerend** (dagmasker 127); ze lopen niet vanzelf af. Het vangnet bij uitval van HEMS is dus een apart wachtwoord-loos watchdog-mechanisme, geen eigenschap van de sloten.
4. **De oude entiteiten laten zich in vier groepen verdelen.** Vervangen door HEMS (battery-manager, energy-prices), laten staan als apparaatlaag (battery-api, SAJ, ocpp_hub, water-heater-scheduler zolang HEMS de boiler niet bestuurt), opruimen (30 Charge Amps-weesentiteiten, 5 NetDaemon-helpers) en omleiden (`sensor.current_price` met zes automations, twee dashboards).
5. **Voorgesteld in zes fases.** Opruimen en omleiden vragen weinig risico en kunnen nu; de batterij-overdracht is de grote stap en krijgt een eigen gate met rollback; de EV volgt na de stroomproef.

## 2. Wat er op de server staat

HA 2026.10.4 (de testplugin staat nog op 2026.10.2; zie 7.4), 1482 entiteiten, 20 geïnstalleerde apps waarvan 18 draaien.

### Apps en integraties rond energie

| Systeem | Versie | Staat | Entiteiten | Rol |
|---|---|---|---|---|
| Battery Manager (add-on) | 0.9.9 | draait | 13 sensors + update | bestuurt de batterij, dashboardtekst |
| Battery API (add-on) | 0.3.5 | draait | 8 sensors, 2 select, 1 number | vertaalt een genormaliseerd schema naar de SAJ (MQTT in, HA-entiteiten uit) |
| Energy Prices (add-on) | 1.6.4 | draait | 11 sensors, 2 binary_sensors + 2 helpers | Nord Pool, importprijs en exportprijs met `price_curve` |
| Water Heater Scheduler (add-on) | 1.3.0 | draait | `input_text.heating_schedule_status`; `sensor.wh_*` ontbreken nu (zie 8) | bestuurt de boiler via `water_heater.home_boiler_dhw_domestic_hot_water` |
| Charge Amps Monitor | geen add-on meer | **weesentiteiten** | 30 (19 met een waarde, 11 onbeschikbaar) | de oude lader, sinds 20 okt uit |
| NetDaemon | geen add-on meer | **weesentiteiten** | 5 input_booleans (aan) + 1 update (onbeschikbaar) | oude apps (energy_battery, energy_appliances, usage_report, vacation) |
| SAJ H2 Modbus (integratie) | – | draait | 279 (200 sensors, 46 numbers, 28 text, 4 switches) | de omvormer zelf |
| OCPP Hub (integratie) | – | draait | 24 | de NEO |
| HEMS (integratie) | build 73ce86f | draait | 22 | dry-run planner |
| Vaillant eBUS, Forecast.Solar, DSMR, kia_uvo | – | draaien | – | boiler en warmtepomp, PV-schatting, meter, auto |

### Wie gebruikt wat

| Oude entiteit | Gebruikt door | Gevolg bij verwijderen |
|---|---|---|
| `sensor.energy_prices_electricity_import_price` en `…_export_price` (met `price_curve`) | het template-helper `sensor.current_price`; de water-heater-add-on (optie `price_sensor_entity_id`); HEMS als terugvalbron en prijscontrole; de lovelace-grafieken | `current_price` valt weg en daarmee zes automations; het boilerschema valt stil |
| `sensor.current_price` (helper) | `Airco aan met lage prijzen`, `Airco aan met prijzen onder nul`, `Airco aan met warm weer`, `Airco uit met hoge prijzen`, `Kachel aan bij prijzen onder 0`, `Kachel uit bij prijs boven 0` | zes automations stoppen |
| `sensor.energy_prices_average_price_today`, `…_max_profit_today`, `…_maximum_price_today` | tegels op het overzichtsdashboard | tegels leeg |
| `sensor.battery_manager_current_action` | tegel op het overzichtsdashboard | tegel leeg |
| `sensor.battery_manager_reasoning`, `_forecast`, `_schedule`, `_schedule_part_2` | dashboard `battery-management` (markdown-kaart) | kaart leeg |
| `sensor.battery_api_battery_soc`, `_battery_power`, `_pv_power` | overzichtsdashboard (tegel en twee mushroom-kaarten); **HEMS zelf** (SoC, batterijvermogen, PV) | dashboard en HEMS-invoer |
| `sensor.charge_amps_monitor_*`, de NetDaemon-helpers | niets (geen automation, script of dashboard gevonden) | niets |
| `sensor.power_usage` | HEMS (netvermogen); is een template op DSMR en onafhankelijk van de oude systemen | n.v.t. |

Scripts (`Battery Info Popup`, `Water opwarmen`, `Say with Alexa`, `Toggle Lamp Eettafel`) verwijzen niet naar de oude entiteiten. Dit gaat over opgeslagen UI-automations en lovelace; YAML-pakketten en bestanden onder `/config` heb ik niet doorzocht.

### Gezondheid van de bestaande besturing (om mee te rekenen)
- `sensor.battery_api_schedule_status` staat op **Apply failed** (laatst toegepast 26 okt 23:43); het stond ook op 5 okt zo. De batterij ontlaadt wel (7,9 kW onder "Adaptive 8000W"). De eigen succesindicator van het schrijfpad is dus niet te vertrouwen en HEMS heeft een eigen terugmelding nodig (gemeten batterijvermogen tegen gevraagd vermogen).
- De water-heater-add-on meldt `legionella last_run=2026-10-17T18:30` met `needs=True use=False` op 27 okt; de zaterdag van 24 okt heeft dus geen legionella-run opgeleverd (oorzaak niet onderzocht).
- Eerder opgemerkt: HA herstart vaak (13 op 18 en 19 okt). Voor een schrijvende planner is dat een ontwerpgegeven (hoofdstuk 5).

## 3. Vervangingskaart: oud naar HEMS

| Functie | Oud | HEMS-equivalent | Dekking |
|---|---|---|---|
| Batterijactie nu | `battery_manager_current_action`, `_mode`, `_status` | `sensor.hems_battery_action` (charge, discharge, idle; reden in attributen), `sensor.hems_executor` | **gedeeltelijk**: HEMS kent geen "adaptive" of "passive" (BM volgt het huisverbruik in real time) |
| Plan en schema | `_charge_schedule`, `_discharge_schedule`, `_schedule`, `_schedule_part_2` | `sensor.hems_plan` (attribuut `markdown`), `hems_charge_window`, `hems_discharge_window`, `hems_sell_window` | ja |
| Uitleg | `_reasoning`, `_decision` | `hems_battery_action` (`reason`, `keep_value_eur_kwh`), `hems_plan` en het decision-spoor | ja, andere vorm |
| Prijsklassen | `_price_ranges` (Load, Passive, Adaptive, Discharge) | geen | **bewust niet**: HEMS plant op één economisch doel |
| Morgen-prognose | `_forecast` | `binary_sensor.hems_tomorrow_prices_available`, `hems_import_price` met `curve` | ja |
| Opdracht/vermogen | `_last_commanded_power`, `_effective_discharge_power` | `sensor.hems_battery_setpoint` (alleen dry-run) | ja, nog zonder schrijfpad |
| Prijs nu en curve | `energy_prices_electricity_import_price` en `_export_price` (`price_curve`) | `sensor.hems_import_price`, `sensor.hems_export_price` (attribuut `curve`) | ja; HEMS' eigen Nord Pool klopt met de add-on op 0,0001 |
| Prijs vandaag min, max, gemiddeld, max winst, prijsniveau | `…_minimum/maximum/average_price_today`, `…_max_profit_today`, `…_price_level` | geen | **mist**: nieuwe sensoren of dashboardtegels vervallen |
| `sensor.current_price` | template op energy-prices | helper omzetten naar `sensor.hems_import_price` | triviaal |
| PV/SoC/batterij/net/belasting | `battery_api_*` (en onderliggend `saj_*`) | HEMS leest die; geen vervanger nodig | apparaatlaag blijft |
| Boilerplan | `wh_heating_plan`, `wh_status` (REST-staat van de add-on) | `sensor.hems_water_heater_plan` (alleen plan) | HEMS plant, de add-on bestuurt nog |
| Laden auto | Charge Amps (weg) | `sensor.hems_ev_*` en `ocpp_hub` | nieuw, nog dry-run |

## 4. De batterij-aansturing: route B

**Besluit (Mark, 27 okt 2026): route B.** HEMS schrijft de entiteiten van de SAJ-integratie (`saj_h2_modbus`) zelf; battery-api hoeft niet te veranderen. Dat past op de HEMS-regel: alleen HA-entiteiten en -services, geen MQTT, geen interne API van een andere add-on. De prijs is dat HEMS de SAJ-kennis krijgt die nu in battery-api zit.

Verworpen: route A (battery-api krijgt een HA-native schema-entiteit via MQTT Discovery) en route C (alleen `select.battery_api_*` en de exportlimiet: geeft geen vermogen of schema).

### 4.1 De entiteiten (uit de Modbus-backend van battery-api, `backends.py`; bestaan op deze server)
| Doel | Entiteit |
|---|---|
| Modus lezen en zetten | `sensor.saj_app_mode` (lezen) en `number.saj_app_mode_input` (zetten): 0 = Self-consumption, 1 = Time-of-use, 12 = AI |
| Laadsloten 1 tot 7 | tijd start en einde als `text`-invoer (`…charge<n>_start_time_input`, `…_end_time_input`), vermogen als `number` in procent (`…_power_percent_input`), dagmasker (`…_day_mask_input`), en `number.saj_charge_time_enable_input` (bitmasker van actieve sloten) |
| Ontlaadsloten 1 tot 7 | hetzelfde met `discharge`, en `number.saj_discharge_time_enable_input` |
| Passieve besturing (alternatief) | `switch.saj_passive_charge_control`, `switch.saj_passive_discharge_control`, `number.saj_passive_battery_charge_power_input`, `number.saj_passive_battery_discharge_power_input`, `number.saj_passive_grid_charge_power_input`, `number.saj_passive_grid_discharge_power_input`, `number.saj_passive_charge_enable_input` |
| Meting voor de terugmelding | `sensor.saj_battery_power`, `sensor.saj_battery_energy_percent`, `sensor.saj_total_grid_power`, `sensor.saj_app_mode`, de uitleesversies van de sloten en `sensor.saj_charge_time_enable_bitmask` |
| Grenzen | `sensor.saj_battery_charge_power_limit`, `…_discharge_power_limit`, `number.saj_export_limit_input` |

### 4.2 Het schrijfprotocol dat battery-api gebruikt (HEMS neemt het over)
1. Per slot (1 tot 7) alleen de velden schrijven die afwijken: starttijd, eindtijd (start + duur), vermogen als percentage van 8000 W (`modbus_inverter_power_w`), dagmasker 127; een ongebruikt slot terug naar 00:00, 00:00, 0 %, masker 0.
2. Daarna het bitmasker van actieve sloten, dan de modus: Time-of-use zodra er een slot is, anders Self-consumption.
3. Terugmelding: de uitleesentiteiten pollen tot ze het schema laten zien (met vertragingen en pogingen); bij een verschil geldt het schrijven als mislukt.
4. Maximaal 7 laad- en 7 ontlaadsloten; dus een plan van 48 uur moet naar de komende uren worden teruggebracht (BM schrijft alleen vandaag).

### 4.3 Wat dit voor HEMS betekent
- **Het uitvoerdersontwerp bestaat al** (`executor.py`: vloer, vol, stale SoC), maar werkt per kwartier op een vermogen. Met tijdsloten wordt het plan in vensters geschreven en bij elke wijziging van plan, SoC of vloer herschreven; de SAJ heeft zelf een ontlaaddiepte van 5 % (`sensor.saj_battery_on_grid_discharge_depth`), de HEMS-reserve van 30 % moet HEMS dus zelf bewaken door een slot te verkorten.
- **De sloten zijn dagelijks terugkerend.** Een slot dat HEMS schrijft en dat HEMS daarna niet meer wist, herhaalt zich de volgende dag op hetzelfde uur. Dat is de situatie van BM nu ook, maar voor een schrijvende planner is een vangnet nodig: (a) HEMS wist zijn sloten bij het stoppen of verwijderen van de integratie; (b) een **watchdog buiten HEMS**: een kleine HA-automation die bij `sensor.hems_status` anders dan `ok` gedurende meer dan een afgesproken tijd de sloten leegt en de modus op Self-consumption zet.
- **Eén schrijver tegelijk.** Zolang battery-manager draait schrijft die via battery-api naar dezelfde entiteiten. Overdracht: BM stoppen (of battery-api in `simulation_mode` zetten, wat hardwareschrijven overslaat) vóór HEMS op auto gaat. Dat battery-api zelf nooit op eigen initiatief schrijft is nog niet bevestigd (zie 8).
- **Telemetrie**: HEMS leest nu `battery_api_*`. Op termijn kunnen die rollen naar `sensor.saj_*` wijzen (SoC `saj_battery_energy_percent`, batterijvermogen `saj_battery_power`, PV `saj_pv_power`, net `saj_total_grid_power`); de recorder-historie van de nieuwe entiteiten is dan korter, wat de belastingsgeschiedenis (7 dagen) raakt. Pas omzetten nadat battery-api is uitgefaseerd.
- **Passieve modus** (een live setpoint) past beter op een kwartier-planning, maar battery-api noemt hem zelf experimenteel en het gedrag bij wegvallen van de besturing is onbekend. Eerst tijdsloten; passief als latere verfijning na meting.

## 5. Wat HEMS nog moet krijgen

| # | Onderdeel | Inhoud |
|---|---|---|
| 1 | **Modus per module en hoofdschakelaar** | `dry-run` (nu), `advisory` (melding en sensor met "dit zou ik sturen"), `auto` (schrijven); één schakelaar of select "HEMS stuurt aan" die alles terugzet naar dry-run; standaard dry-run |
| 2 | **Schrijflaag per apparaat** | Eén module, alleen HA-services, met een toegestane lijst entiteiten uit de config, een schrijfbudget en idempotente opdrachten; elke schrijfactie komt in het spoor (`write`-event met doel, waarde, uitkomst) |
| 3 | **Batterij-uitvoerder (SAJ, route B)** | Maakt van het plan sloten volgens het protocol van 4.2, controleert vóór het schrijven de live SoC en vloer (`executor.py` bestaat al), leest de SAJ-entiteiten terug en vergelijkt gemeten vermogen met gevraagd; wist zijn sloten bij stoppen |
| 4 | **Overdracht aan één besturing tegelijk** | BM en HEMS mogen niet tegelijk schrijven. Het moment van overdracht is een expliciete stap met rollback |
| 5 | **Fail-safe bij herstart en uitval** | Bij `no_soc`/`stale`/herstart: niets nieuws schrijven; bij start geen oud schema herhalen; de sloten zijn dagelijks terugkerend en lopen niet vanzelf af, dus HEMS wist zijn sloten bij stoppen en een watchdog buiten HEMS leegt ze bij uitval (4.3) |
| 6 | **Gesloten-lus-test** | De huidige bewijzen zijn replay met orakel en planvergelijking. Eerst één begeleide dag in advisory (schema loggen en vergelijken met wat BM echt deed), dan één dag auto met Mark erbij |
| 7 | **Wat BM extra doet** | Adaptive/passive bijsturen op het huisverbruik; HEMS plant vermogen per kwartier. Eerst meten of dat verschil iets kost of oplevert (aansluiten op het margeverhaal) |
| 8 | **Prijssensoren en dashboards** | Min, max, gemiddeld vandaag en max winst als HEMS-sensoren (of tegels laten vervallen); nieuw dashboard op HEMS; `current_price` omzetten |
| 9 | **Boiler** | Twee opties: de water-heater-add-on laten sturen (met HEMS-prijs als bron) of een HEMS-boileruitvoerder bouwen die `water_heater.set_temperature` schrijft en de legionella-, bad-, away- en negatieve-prijsregels van de add-on overneemt. Het laatste is veel werk met weinig winst nu |
| 10 | **EV-uitvoerder** | `number.set_value` op de laadlimiet en de schakelaar, na de stroomproef en met het vangnet uit het EV-onderzoek (geldigheidsduur of dagschema) |

## 6. Gefaseerd plan

Elke fase eindigt met een gate: wat bewezen moet zijn, wat Mark zelf moet goedkeuren, en hoe het terug kan.

**Fase 0, opruimen (nu, geen risico voor besturing).** Verwijder de 30 weesentiteiten van Charge Amps en de 5 NetDaemon-helpers met de update-entiteit. Eerst per groep controleren dat niets ernaar verwijst (gedaan voor automations, scripts en dashboards; YAML-bestanden niet). De Charge Amps-entiteiten komen waarschijnlijk uit bewaarde MQTT Discovery-berichten; verwijderen uit het register zonder het retained bericht te wissen levert ze terug bij de volgende herstart (nog te controleren). Gate: Marks ja op de lijst. Rollback: niet nodig.

**Fase 1, prijzen omleiden.** `sensor.current_price` en de boiler-optie `price_sensor_entity_id` naar `sensor.hems_import_price`, eventueel nieuwe min/max/gemiddelde-sensoren, dashboardtegels naar HEMS. Daarna de energy-prices-add-on stoppen (niet verwijderen) en een week meekijken. Gate: de zes automations triggeren zoals voorheen; HEMS' prijs blijft binnen 0,0001 van de oude. Rollback: de add-on weer starten, helper terugzetten. Let op: HEMS heeft nu `price_curve_entity` als terugvalbron; die rol moet dan weg of naar iets anders wijzen.

**Fase 2, dashboards.** Een HEMS-dashboard (plan, acties, EV, boiler) naast het oude; daarna het oude `battery-management` en de BM-tegels vervangen. Geen risico voor besturing.

**Fase 3, schrijflaag en modus bouwen (dry-run blijft).** Items 1, 2, 3 en 5 uit hoofdstuk 5: de SAJ-uitvoerder volgens 4.2 met een nepdienst in de tests, de watchdog-automation, en de test-plugin naar 0.13.375. Battery API blijft ongewijzigd. Alles achter modus `dry-run`; unit- en HA-tests met een nepdienst. Gate: tests, onafhankelijke review en audit (dit is vrijgave-gevoelig), `Apply failed` verklaard, en de vraag of battery-api zelf schrijft beantwoord (hoofdstuk 8).

**Fase 4, batterij: advisory, dan auto (Mark erbij).**
1. *Advisory*: HEMS publiceert het schema dat het zou schrijven (`text`-waarde in een sensor) en logt het verschil met wat BM stuurde. Een paar dagen meekijken.
2. *Overdracht*: BM stoppen, HEMS op auto voor de batterij, op een dag met een duidelijk piekverschil en Mark aanwezig. Alle schrijfacties staan in het spoor; hoofdschakelaar uit = terug naar dry-run en BM starten.
3. Een week meten: cash, kWh per dag, verkooptijd (stap 3c) tegen het BM-archief.
Gate: Marks ja per stap. Rollback: BM weer starten en HEMS op dry-run; het schema van HEMS loopt vanzelf af.

**Fase 5, boiler en EV.**
- Boiler: de add-on laten staan als uitvoerder met HEMS-prijs; HEMS controleert zijn plan tegen `sensor.wh_heating_plan`. Een HEMS-boileruitvoerder is een aparte beslissing.
- EV: stroomproefreeks (6, 8, 12, 16, 6 A, pauze op 0 A, `duration`, `GetCompositeSchedule`), dan advisory, dan auto. De NEO staat nog op 10 A; eerst wissen.

**Fase 6, afbouwen.** battery-manager en energy-prices verwijderen (na een rustige periode), repository-docs bijwerken (AGENTS.md, install.md, README van de add-ons), HEMS-versie vastzetten en een releaseproces voor de integratie.

## 7. Voorwaarden, risico's en beslissingen

### 7.1 Risico's
| Risico | Wat ervan te verwachten is | Dempen |
|---|---|---|
| Twee besturingen schrijven tegelijk | batterij vecht met zichzelf, schema's overschrijven elkaar | één overdrachtsmoment, BM gestopt vóór HEMS schrijft; HEMS schrijft nooit als BM-sensoren nog verversen |
| Schrijfpad meldt `Apply failed` | HEMS denkt dat het stuurt en het gebeurt niet | eigen terugmelding op gemeten vermogen, alarm bij afwijking |
| HA herstart of HEMS valt uit midden in een schema | half geschreven of achtergebleven slot dat dagelijks terugkeert | idempotent schrijven, terugmelding, geen herhaling van oude sloten bij start, wissen bij stoppen en een watchdog buiten HEMS (4.3) |
| Plan op verouderde of ontbrekende data | verkeerd vermogen | bestaande stale- en no_soc-regels tellen ook voor schrijven; nooit schrijven bij een status anders dan `ok` |
| Prijsmodel verandert op 1 januari 2027 | export wordt goedkoper dan import | `salderen_until` staat klaar; eerst meten wat HEMS en BM daarna doen |
| Verlies van functies van BM | adaptief volgen van het verbruik, prijsklassen | bewust besluit per functie, zie 5.7 |

### 7.2 Voorwaarden vóór auto
- Een schrijflaag met modus per module en een hoofdschakelaar die alles uitzet.
- Een bewezen schrijfpad naar de omvormer (route B, 4.2) met terugmelding en een werkende watchdog.
- Een begeleide proefdag in advisory, een dag in auto met Mark erbij.
- Een onafhankelijke review en audit van de schrijflaag (release-gevoelig).
- Marks expliciete ja per module en per stap; geen automatische overgang.

### 7.3 Vragen voor Mark
1. ~~Batterij-route~~ **Beslist: B** (HEMS schrijft de SAJ-entiteiten zelf, 27 okt 2026).
2. **Boiler**: de water-heater-add-on laten sturen met HEMS-prijs, of op termijn laten opgaan in HEMS?
3. **Prijssensoren**: min, max, gemiddeld en max winst als HEMS-sensoren bouwen, of de dashboardtegels laten vervallen?
4. **Weesentiteiten**: Charge Amps (30) en NetDaemon (5 helpers) verwijderen? Is er iets van NetDaemon (bijvoorbeeld `vacation_alarm`) dat nog moet draaien?
5. **Legionella**: de run van zaterdag 24 okt ontbreekt (laatste 17 okt); wil je dat uitgezocht hebben vóór de boiler verder meeverhuist?
6. **Overdrachtsdag**: welke dag past voor de batterij-overdracht (een dag met een duidelijk piekverschil en jij thuis)?

### 7.4 Overig
- **Testplugin**: de server draait 2026.10.4; de plugin `pytest-homeassistant-custom-component==0.13.373` pint 2026.10.2. Release `0.13.375` pint 2026.10.4. Bijwerken in de venv (`.claude/venv/ha`) en in `hems/AGENTS.md`.
- **Branches**: `feature/hems-ev-module` is gepusht, niet gemerged; dit document staat nog los van die branch.
- **Docs bijwerken bij de start**: `hems/AGENTS.md` ("alleen dry-run" wordt per module), `docs/hems/install.md`, het geheugen `project_hems-module-plan.md`.

## 8. Niet geverifieerd

- Waarom `Apply failed` blijft staan terwijl de batterij wel reageert.
- Of `sensor.wh_*` en `sensor.wh_heating_plan` ontbreken omdat de add-on ze via de REST-staat plaatst (die verdwijnen bij een HA-herstart en komen terug bij de volgende wijziging of het uurlijkse bericht) of door een fout; het log van 07:41 zegt "Heating plan published", en HA is om 08:12 herstart.
- Of de weesentiteiten van Charge Amps en NetDaemon uit het register of uit retained MQTT-berichten komen.
- Of YAML-bestanden in `/config` (pakketten, `configuration.yaml`) nog naar de oude entiteiten verwijzen; alleen de opgeslagen automations, scripts, dashboards en helpers zijn gescand.
- Wat de omvormer doet als de besturing wegvalt in passieve modus, en of de tijdsloten van de SAJ-integratie het gewenste vermogen per kwartier nauwkeurig genoeg volgen.
- Of battery-api zelf op eigen initiatief naar de SAJ-entiteiten schrijft (bij start, "safe provider cutover", herstel van een afwijking) terwijl BM gestopt is; dat moet bekend zijn voor de overdracht. Ook of het dagmasker 127 de enige instelling van battery-api is (de optie `schedule_days: today` hoort bij een andere route) en of de SAJ een slot met een eindtijd voor de starttijd (over middernacht) aanvaardt.
- Het gedrag van BM's adaptive modus ten opzichte van een kwartier-planning in een gesloten lus.
- De rest van het gedrag van de NEO bij stuurstromen (stroomproef nog niet gedaan).
