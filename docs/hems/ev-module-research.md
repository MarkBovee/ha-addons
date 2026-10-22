# EV-module voor HEMS: onderzoek op basis van ocpp-hub (22 okt 2026)

Status: **onderzoek, niets gebouwd, niets geschreven** naar de lader of naar Home Assistant. Alle HA-waarden zijn alleen gelezen (HA MCP, 22 okt 2026). Wat ik niet kon controleren staat in hoofdstuk 8.

Bronnen: `/mnt/work/Projects/Personal/ocpp-hub` (branch `feature/schedule`, `custom_components/ocpp_hub/*.py`, `core/control.py`, `core/readings.py`, `docs/roadmap.md`, `docs/dashboard.md`, `docs/developer.md`, `docs/plan-handoff.md`), de HEMS-engine in `hems/core/hems/` (`balancer.py`, `dryrun.py`, `heater.py`, `rolling.py`, `battery.py`, `contracts.py`), `custom_components/hems/` en de HA-entiteiten zelf.

## 1. Samenvatting en aanbeveling

1. **Eén EV-planner, geen drie losse regelsets.** Laden onder een prijs, laden op PV-overschot en laden voor een deadline zijn drie *getarifeerde termen* in dezelfde planner (`hems/core/hems/ev.py`, zuiver, zoals `heater.py`): een verplichte energiehoeveelheid voor de deadline, een opportunistische extra hoeveelheid onder een prijsdrempel, en per kwartier een effectieve prijs waarin overschot goedkoper is dan net. Dat past bij de HEMS-regel dat een beperking een geprijsde term is met een reden in de trace, geen stil kandidaatfilter.
2. **PV-overschot wordt een basiscomponent `base_solar`, geen module** (antwoord op Marks vierde punt, zie 4.2). Een module stelt iets voor dat HEMS kan sturen; PV kan HEMS niet sturen. De component levert gemeten PV (meerdere entiteiten of één totaal), de verwachting per kwartier en het overschot. Batterij en EV lezen allebei daaruit.
3. **Volgorde per cyclus:** huisbasis en PV-verwachting, boiler (bestaat), **EV-plan**, batterijplan met EV en boiler als vaste last (net zoals `heater.py` de runs in `load_kwh` zet), daarna de balancer als grenscontrole. De batterij-DP blijft ongewijzigd, op één punt na: een per-kwartier plafond op laden uit het net (4.5).
4. **Load balancing moet per fase, in ampère.** `balancer.allocate` rekent in totaal-watt met 15 kW; de aansluiting is 3x25 A (17,25 kW totaal, maar 25 A per fase). Een EV op 16 A neemt 16 A op elke fase; de zwaarst belaste huisfase bepaalt de ruimte. Daarvoor ontbreekt nu **meetdata per fase** (hoofdstuk 3): de DSMR-entiteiten voor stroom per fase bestaan maar zijn door de integratie uitgezet.
5. **Alleen dry-run**, in drie stappen (hoofdstuk 6). Schrijven naar de lader blijft buiten dit plan tot na een stroomproefreeks en Marks ja.

## 2. Inventarisatie ocpp-hub

Charger-id `ED13009A`; entity_id-patroon `<domein>.ocpp_hub_<slug(cp_id)>_<key>`, hier slug `ed13009a` (bevestigd in HA). De sleutel is stabiel (staat in de code vast, niet taalafhankelijk). Eén apparaat per lader. Sensoren zijn *niet beschikbaar* zolang de lader niet verbonden is (behalve `connected`, `last_session`).

| entity_id (`…` = `ocpp_hub_ed13009a_`) | Domein | Eenheid / semantiek | R/W | Rol voor HEMS | Live (22 okt) |
|---|---|---|---|---|---|
| `binary_sensor.…connected` | binary_sensor | lader heeft open verbinding met de hub | R | status (beschikbaarheid, altijd beschikbaar) | on |
| `binary_sensor.…plugged_in` | binary_sensor | auto aangesloten; afgeleid van de status (`preparing`, `charging`, `suspended_*`, `finishing` = aan, `available` = uit, anders onbekend) | R | status, realtime vervanger van `ev4_ev_battery_plug` | off |
| `binary_sensor.…car_charging` | binary_sensor | status is `charging` | R | status | off |
| `binary_sensor.…problem` | binary_sensor | `faulted` of foutcode ≠ `NoError` | R | status (planner pauzeert bij aan) | off |
| `sensor.…status` | sensor (enum) | `available, preparing, charging, suspended_evse, suspended_ev, finishing, reserved, unavailable, faulted` | R | status | available |
| `sensor.…error_code` | sensor (enum, diagnostisch) | OCPP-foutcode als sleutel | R | status | no_error |
| `sensor.…power` | sensor, W, measurement | actief vermogen; **0 W** zolang het contact niets levert (feit, geen ontbrekende waarde) | R | meting (vervangt `charge_amps_monitor_charger_current_power`) | 0.0 |
| `sensor.…energy` | sensor, kWh, total_increasing | energieregister van de lader | R | meting (SoC-schatting tussen auto-updates) | 5.105 |
| `sensor.…current_l1/_l2/_l3` | sensor, A, measurement | stroom per fase van de lader; 0 voor een fase die de meter weglaat | R | meting (EV-aandeel per fase) | 0.0 |
| `sensor.…voltage_l1/_l2/_l3` | sensor, V | spanning per fase | R | meting; **standaard uitgeschakeld** | disabled |
| `sensor.…current_offered` | sensor, A | stroom die de lader de auto aanbiedt (meetwaarde `Current.Offered`) | R | status/terugmelding van het setpoint | unknown |
| `sensor.…limit_in_effect` | sensor, A | geldende limiet: wat de lader zelf meldt (`GetCompositeSchedule`) anders het laagste van hub- en leverancierslimiet; attributen `hub_limit_a`, `vendor_limit_a`, `charger_reported_a`, `source` (`charger`/`calculated`), `restored_unconfirmed`, `schedule` | R | terugmelding (is mijn setpoint toegepast?) | 10.0 |
| `number.…charge_limit` | number, A, bereik 0 tot plafond (nu 16), stap 1, mode box; **onder 6 A = pauze (0)**; attributen `pauses_below_a` (6), `profile_purpose`, `vendor_limit_a`, `restored_unconfirmed` | **R/W** | **setpoint** | 10.0 (zie 8) |
| `switch.…charging` | switch | aan = laadsessie loopt; aan zetten = `RemoteStartTransaction`, uit = `RemoteStopTransaction`; start werkt alleen met auto aangesloten | **R/W** | setpoint (start/stop) | off |
| `button.…clear_charge_limit` | button | wist het profiel van de hub (profiel-id 7001); alleen dit profiel | W | noodknop, niet voor HEMS | – |
| `sensor.…current_session` | sensor, kWh | energie van de lopende sessie; attributen `transaction_id`, `started_at`, `duration_s`, `max_power_w`, `average_power_w`, `max_current_a`, `offered_a`, `limit_a` | R | meting | unknown |
| `sensor.…last_session` | sensor (timestamp) | einde laatste sessie; attributen incl. `recent_sessions` (20 stuks), `session_count`, per sessie `energy_kwh`, `duration_s`, `max_power_w`, `stop_reason` | R | historie voor de replay | 2026-10-21 11:29 UTC |
| `sensor.…mirror_status`, `…mirror_queue` | sensor (diagnostisch) | staat van de kopie naar Raedian, wachtrij | R | niet voor HEMS | connected, 0 |
| `sensor.…model`, `…firmware` | sensor (diagnostisch) | uit BootNotification | R | niet voor HEMS | NEO_22T_A |
| service `ocpp_hub.set_schedule` | service | dagschema met perioden (`time`, `limit`) als herhalend profiel onder het plafond | W | **vangnet** voor later (zie 7.3) | – |
| service `ocpp_hub.get_sessions` | service | volledige sessiehistorie, optioneel per lader | R (antwoord) | replay-invoer | – |

Relevante eigenschappen van de schrijfroute (`core/control.py`):
- Eén bewaakt schrijfpad; elke waarde boven het plafond (`max_current` uit de opties van ocpp-hub, standaard 16 A) wordt geweigerd (`above_ceiling`), geen getal of negatief ook. Een wens tussen 0 en 6 A wordt **0 A (pauze)**.
- Profielvolgorde: eerst `ChargePointMaxProfile` (stationsplafond, connector 0), terugval `TxProfile` of `TxDefaultProfile` (connector 1). Wat de lader accepteert wordt onthouden (`profile_purpose`). Op de NEO is `ChargePointMaxProfile` geaccepteerd (attribuut staat zo).
- Het getoonde setpoint is **wat de lader voor het laatst accepteerde op deze verbinding**; na een herverbinding of herstart staat er niets tot het opnieuw wordt gezet (`restored_unconfirmed`). HEMS moet het setpoint dus idempotent elke cyclus bevestigen en `limit_in_effect` als waarheid lezen, niet de number.
- De lader past het laagste toe van hub- en leverancierslimiet. Opdrachten van Raedian worden standaard geweigerd (`vendor_commands = reject`); de mirror is alleen-lezen.
- Bewezen op de NEO (roadmap, 21 okt): eerste echte lading, station-profiel van 6 A gehoorzaamd (5,9 A per fase, ca. 4,05 kW), statusreeks preparing, charging, suspended by car, finishing, available; 5,0 kWh in 84 minuten (gemiddeld 3,6 kW). **Onbewezen**: wijzigen van de limiet tijdens een lopende lading, 6 naar 16 A, pauze op 0 A, `GetCompositeSchedule`, herhalend dagschema.

### Wat HEMS mist of anders wil (wensen voor ocpp-hub, niet voor HEMS)

| Wens | Reden | Ernst |
|---|---|---|
| Profiel met **geldigheidsduur** (`chargingSchedule.duration`, bv. 30 min) dat HEMS elk kwartier ververst, en een `last_accepted_at` attribuut | Een gestorven HEMS laat anders het laatste setpoint staan (16 A + piek in het huis = zekering). Of de NEO `duration` honoreert is onbekend | hoog voor auto-modus, niet voor dry-run |
| Een number met bereik 6 tot plafond (Marks voorstel) plus een apart "laden toegestaan" | De huidige number loopt van 0 tot het plafond en zet alles onder 6 A om in pauze. Dat is een ruimer bereik dan nodig, maar het werkt: HEMS schrijft alleen 0 of 6 tot plafond en leest `pauses_below_a` en het `max` van de number. **Geen wijziging nodig** | laag |
| Stroom per fase van het **huis** | Zit niet in ocpp-hub en hoort er niet in; komt uit de DSMR-meter | zie hoofdstuk 3 |
| Terugmelding "setpoint toegepast" met tijd | HEMS wil weten of het verzoek binnen X seconden zichtbaar werd in `current_offered` | middel |

## 3. Overige invoer en wat er in HA aanwezig is

| Invoer | Entiteit (gecontroleerd 22 okt) | Opmerking |
|---|---|---|
| Auto-SoC | `sensor.ev4_ev_battery_level` (nu 100 %) | kia_uvo, cloud-poll: kan minuten tot een half uur achterlopen. Eenheid % |
| Aangesloten (auto) | `binary_sensor.ev4_ev_battery_plug` (off) | idem vertraagd; voor HEMS is `binary_sensor.ocpp_hub_ed13009a_plugged_in` realtime en leidend |
| Auto laadt | `binary_sensor.ev4_ev_battery_charge` (off) | idem; `…car_charging` is leidend |
| Accucapaciteit | `sensor.ev4_ev_battery_capacity` = **293040** | eenheid onduidelijk. 293040 / 3600 = 81,4 kWh, wat de EV4 Long Range is: waarschijnlijk kJ, **niet bevestigd**. `sensor.ev4_ev_battery_level_2` = 275882,4 (resterende energie, zelfde eenheid) |
| Doel-SoC van de auto | `number.ev4_ac_charging_limit` (100) | schrijfbaar in kia_uvo; HEMS leest het alleen als plafond van de eigen doelstelling |
| Vertrektijd | `sensor.ev4_ev_first_scheduled_departure_time` (07:30:00), `…second…` (12:00:00); schakelaars `switch.ev4_ev_scheduled_departure_1/2` staan uit | bruikbare bron voor de deadline; of de tijden bijgewerkt zijn is onbekend |
| Laadstroomlimiet auto | `sensor.ev4_ev_charging_current_limit` (100) | betekenis (% of A) onbekend |
| Netvermogen | `sensor.power_usage` (template-helper op de DSMR-meter) is wat HEMS nu als netvermogen gebruikt; `sensor.electricity_meter_power_consumption/_production` (W, totaal) | + import / − export. De helper heeft in het register een eenheid `kWh` (vreemd voor een vermogen; HEMS werkt er al mee, niet nagegaan) |
| **Netstroom per fase** | `sensor.electricity_meter_current_phase_l1` (Stroom fase L1) en `sensor.electricity_meter_power_consumption_phase_l1` (Energieverbruik Fase L1) bestaan **maar zijn `disabled_by: integration`**. L2 en L3 zijn niet gecontroleerd (zelfde patroon verwacht). Alleen de spanning per fase (224,8 / 226,4 / 226,1 V) staat aan | **Dit is het gat.** Inschakelen is een HA-schrijfactie en vraagt Marks ja. DSMR-stroom is een grootte zonder teken; het teken (import of export per fase) komt uit de vermogenssensoren per fase positief/negatief, ook uitgeschakeld |
| PV | `sensor.battery_api_pv_power` (nu in HEMS), daarnaast `sensor.saj_pv_power`, `sensor.saj_fast_pv_power` | één omvormer (SAJ); de panelen haalden maximaal 4964 W |
| Batterij | `sensor.battery_api_battery_soc`, `…battery_power`; SAJ 25 kWh, max 8 kW | of de SAJ driefasig is en hoe symmetrisch hij laadt: niet nagegaan |
| EV-vermogen in HEMS | `CONF_EV` staat in de installatie op `sensor.charge_amps_monitor_charger_current_power`, die sinds 20 okt 14:35 dood is | het huisbasisverbruik bevat sindsdien het laden van de NEO (zie 7.1) |

## 4. Ontwerp

### 4.1 Plaats in de bestaande engine

Hetzelfde patroon als de boiler (`heater.py`), zodat modules voorstellen en de engine het ene huisplan maakt.

| Onderdeel | Wijziging |
|---|---|
| `hems/core/hems/ev.py` (nieuw, zuiver, geen HA-imports, geen merknamen) | `EvConfig`, `EvState`, `EvQuarter`, `EvPlan`, `plan_ev(prices, solar, now, config, state, limits) -> EvPlan`, `ev_kwh_per_quarter(plan)` |
| `dryrun.py` | `EngineSettings.ev: EvConfig` (standaard uit), `EngineInputs.ev: EvState \| None`, `EngineOutput.ev_plan`; `_load_forecast` telt de geplande EV-kWh bij `load_kwh` op (zoals `run_kwh_per_quarter` voor de boiler); `step()` plant EV vóór `plan_next` |
| `balancer.py` | uitbreiden naar fasen, zie 4.5 |
| `custom_components/hems/config_flow.py` | nieuwe sectie `module_ev` in `SECTIONS`, eerste veld `ev_enabled`; daarna doel-SoC, deadline, prijsdrempel, min/max stroom, hold-tijden, entiteitsrollen (zie 4.6). Basis: `base_forecast` wordt `base_solar` (4.2) |
| `coordinator.py` | verzamelt de `EvState` uit de entiteiten (alleen lezen), voegt `ev` toe aan het besluitrecord |
| `sensor.py` | `sensor.hems_ev_plan` (zoals `hems_water_heater_plan`), `sensor.hems_ev_setpoint` (A die verstuurd zou worden, na de grenscontrole), `sensor.hems_ev_status` |
| `decision_log.py` | EV-record per kwartier: tier, effectieve prijs, overschot, gekozen stroom, reden, geknepen door (balancer) |

Het contract blijft vendor-vrij. De EV-poort in `contracts.py` krijgt alleen wat HEMS nodig heeft: `plugged`, `charging`, `power_w`, `phase_current_a`, `setpoint_limits (min_a, max_a)`, `soc_pct`, `energy_total_kwh`. Welke HA-entiteit dat is, kiest de gebruiker in `module_ev`; een andere lader met een number in ampère en een vermogenssensor werkt dus ook.

### 4.2 Basiscomponent `base_solar` (antwoord op punt 4)

Ja, handig, maar als **basiscomponent**, niet als module. Het is nu: één PV-entiteit (`CONF_PV`), een gewonnen PV-factor uit het weer in `base_forecast`, `pv_max_ac_w`. De component wordt:

- **Invoer**: een lijst PV-vermogensentiteiten (sommeren) *of* één totaalentiteit; bij beide wint de totaalentiteit. Bij deze installatie is er één omvormer, dus de meerwaarde is nu klein, maar hetzelfde patroon lost ook het EV-vermogen op (nu: Charge Amps vervangen door NEO, historie van beide nodig, zie 7.1). Een gedeelde "som van entiteiten"-selector dient dus PV en EV.
- **Uitvoer** (alles bestaat deels al): gemeten PV (W), verwachting per kwartier (kWh, uit `pvforecast.py`), gekalibreerde factor, en nieuw het **overschot**: voorspeld = max(PV − huisbasis − boiler, 0) per kwartier; live = export + huidig EV-vermogen + batterij-laadvermogen (wat er zou terugvloeien als EV en batterij stil stonden).
- **Niet nu**: per-array tilt/azimut, curtailment. De voorspelling blijft de simpele irradiantie-factor (7,4 W per W/m²); de PV-bias wisselt van teken (21 okt), dus geen kalibratie uitbreiden voordat de EV het nodig heeft.
- **Migratie**: de opties zijn plat opgeslagen, een sectie hernoemen raakt de opgeslagen waarden niet. `CONF_PV` blijft werken als de lijst met één element.

### 4.3 De EV-planner: drie functies als termen van één plan

Invoer per cyclus: `EvState` (aangesloten, SoC schatting, capaciteit, doel-SoC, deadline, huidige stroom, plafond), prijzen per kwartier (`PriceSeries.import_eur_kwh`, `export_eur_kwh`), overschot per kwartier uit `base_solar`.

1. **Energiebehoefte.** `need_kwh = (doel_soc − soc) × capaciteit / rendement_laden`. Rendement AC naar accu schat ik op 0,90 tot 0,92; **te meten** door lader-kWh te leggen naast de SoC-sprong van de kia. SoC-tussen-updates: `soc_schatting = laatste_auto_soc + Δenergie_lader × rendement / capaciteit`.
2. **Mogelijke stroom per kwartier**: {0} ∪ [6 A, plafond] in stappen van 1 A; vermogen = 3 × spanning × stroom (230 V, of de gemeten spanning) = **6 A ≈ 4,1 kW, 16 A ≈ 11,0 kW**. De NEO laadt hier driefasig (bevestigd: 5,9 A per fase, 4,05 kW).
3. **Effectieve prijs van een kwartier bij vermogen P**: `(min(P, S) × export + max(P − S, 0) × import) / P`, met S het overschot van dat kwartier. Zonder overschot is het de importprijs; met overschot ≥ P de exportprijs (de gemiste opbrengst). Daarmee is "laden op PV-overschot" geen aparte stand maar volgt uit de prijs, en wordt vanzelf waardevoller zodra de exportprijs daalt (zie 7.6).
4. **Twee lagen**:
   - *Verplicht* (`deadline`): de goedkoopste kwartieren vóór de deadline die `need_kwh` leveren; vol vermogen in het goedkoopste, een deelkwartier voor de rest (nooit onder 6 A: dan schuift de rest naar het volgende goedkoopste). Is het niet haalbaar binnen de bekende prijzen, dan laadt het zo vroeg als nodig ("urgent", met reden). Prijzen van morgen zijn pas na ca. 13:15 bekend: een deadline voorbij de bekende prijzen mag de verplichte energie op een gegarandeerd minimum zetten en de rest later laten volgen.
   - *Opportunistisch* (`max_price_eur_kwh` en `target_soc_max`): extra energie boven de verplichte laag, alleen in kwartieren waar de effectieve prijs ≤ de drempel. "Laden onder een prijs" is deze laag zonder deadline.
   - Optioneel `solar_only`: opportunistische laag alleen als S ≥ minimaal vermogen (4,1 kW). Dat is de enige harde grens in de planner en wordt in de reden gezegd.
5. **Wachtkosten** (`hold_cost`) zoals bij de batterij: bij gelijke prijs liever laat dan vroeg laden, en een kleine voorkeur om niet op 100 % te staan. Replan elk kwartier met de werkelijke staat; alleen het eerste kwartier telt, zoals `rolling.py`.
6. **Hysterese**: minimaal N minuten aan en uit (instelbaar), stroomwijziging pas bij ≥ 1 A verschil en niet vaker dan eens per kwartier. Een deadline-urgent kwartier overstemt de hysterese.

Waarom geen drie losse regelmodules: ze zouden hetzelfde kwartier claimen met verschillende stromen, de trace zou drie redenen hebben, en de prioriteit tussen "onder X euro" en "voor 07:30 klaar" ontstaat dan door volgorde van uitvoering in plaats van door prijs.

### 4.4 Samenwerking met de batterijplanner

De batterij-DP rekent per kwartier `net = load − pv` en dus ook de EV mee zodra die in `load_kwh` zit. Aanbevolen, in deze volgorde:

1. EV plannen op de importprijs en het overschot (batterijgedrag nog niet bekend).
2. Batterij plannen met EV en boiler als vaste last. De DP ontlaadt dan vanzelf ook voor de EV als dat loont (de EV-kWh vermijdt import), en verkoopt niet wat de EV nodig heeft.
3. **Optioneel, één iteratie**: kwartieren waar de batterij exporteert (`grid_kwh < 0`) krijgen voor de EV de *exportprijs* in plaats van de importprijs (die kWh komt dan uit de batterij), en de EV wordt opnieuw gepland. Eerst meten of dit in replay iets scheelt voordat het erin gaat.

Overschot: EV en batterij willen allebei de middag. Rechtstreeks in de auto gaat zonder omweg (de batterij verliest ongeveer 18 % op de rondgang, rendement 0,82), dus bij een echte behoefte wint de EV het overschot van de batterij. Dat volgt uit de volgorde (EV plant eerst), niet uit een regel; de batterij ziet het overschot al verminderd. Een verfijning voor later: de opportunistische drempel koppelen aan de marginale waarde van opgeslagen energie (`stored_value` uit de DP).

Alternatief overwogen en verworpen: **gezamenlijke DP** met SoC × EV-energie als toestand. Dat is ongeveer 100 × 80 toestanden × 192 kwartieren × acties in zuiver Python, ruim te traag per cyclus. De sequentiële aanpak met één prijsiteratie is bij een EV die vooral een kwestie van "goedkoopste kwartieren" is vrijwel even goed.

### 4.5 Load balancing per fase

Probleem: de EV op 16 A en de batterij die uit het net laadt (8 kW) komen samen op ongeveer 19 kW, boven 17,25 kW, en per fase zit je al op ca. 27 A als de SAJ symmetrisch laadt (**aanname, niet nagegaan**). Op 20 okt laadde HEMS tussen 11:15 en 14:45 met 3,3 tot 7,7 kW, precies de goedkoopste kwartieren waar de EV ook naartoe wil.

Twee lagen, omdat een plan met voorspelde last niet genoeg is:

1. **Planniveau** (voorspeld): per kwartier een plafond `max_charge_kwh` op laden uit het net, als vaste kolom in `Slot` (naast `reserve_soc`). Het is een fysieke grens, geen kandidaatfilter, en komt met reden in de trace. De DP blijft verder ongewijzigd.
2. **Live** (gemeten, elke cyclus en bij elke nieuwe meting, zoals de batterij-executor): `balancer.allocate` uitbreiden naar fasen.
   - Elke last krijgt een aandeel per fase (`phase_share=(a, b, c)`): EV en batterij gelijk (1/3 elk, driefasig), de boiler op de fase(n) waar hij aan hangt (te meten).
   - Ruimte per fase = `limiet_A × spanning − huis_fase − som(toegekend × aandeel)`; een last krijgt wat de krapste fase toelaat. Zonder meetdata per fase: terugval op het totaal en de **conservatieve aanname dat het hele huis op één fase hangt** (EV-stroom ≤ 25 A − totale huisstroom).
   - Huis per fase = netstroom per fase − (EV-stroom per fase uit ocpp-hub) − (batterij als symmetrisch). Dat vraagt het teken per fase (zie 3), anders kan export een fase "zwaar" laten lijken.
   - Hysterese en `min_w` blijven (EV: 6 A × 3 × 230 = 4,14 kW; een draaiende last blijft aan tot 500 W onder min).
   - Marge: standaard 1 A tot 2 A onder 25 A (de zekering lost niet direct uit, maar de meter en de OCPP-reactietijd lopen achter).
3. **Standaardprioriteit** (lager getal = belangrijker, per module instelbaar, nu alleen voorstel): huis (niet regelbaar) 0, EV *met urgente deadline* 1, boiler 2, batterij laden uit net 3, EV opportunistisch 4. Reden: de batterij kan zonder schade later laden, de boiler heeft comfort- en legionellaregels, de auto heeft een tijdgrens. Dit is Marks keuze (hoofdstuk 7).

### 4.6 Instellingen (`module_ev`), uitvoer en trace

Opties: `ev_enabled` (uit), doel-SoC verplicht (80 %), doel-SoC maximaal (100 %), deadline (leeg = uit; bron: kia-vertrektijd, helper of vaste tijd), `ev_max_price` (leeg = uit), `ev_solar_only` (uit), min/max stroom (6 / plafond uit de number), min tijd aan/uit, rendement laden, prioriteit. Entiteitsrollen in dezelfde sectie met entity-selectors: `plugged`, `charging`, `power`, `energy`, `phase_current_l1..3`, `setpoint_number`, `soc`, `capacity`, `target_limit`. Standaardwaarden de ocpp_hub- en kia_uvo-ids uit hoofdstuk 2 en 3.

Uitvoer in dry-run: `sensor.hems_ev_plan` (zin in HA-taal en lokale tijd, bv. "Laden 11:15 tot 13:30 op 6 tot 11 A · klaar 07:30 mogelijk"), attributen met kwartieren (`start`, `current_a`, `kwh`, `effective_price`, `surplus_kwh`, `tier`, `reason`); `sensor.hems_ev_setpoint` (A, na de balancer, met `planned_a`, `clamped_by`); `sensor.hems_ev_status` (`idle`, `not_plugged`, `charging_as_planned`, `waiting_for_cheaper`, `deadline_urgent`, `no_soc`, `problem`). Per besluit komt een `ev`-blok in `decision_trace.jsonl`, met de HEMS-regels voor uitlegbaarheid: de gelogde cijfers zijn dezelfde als in de reden, en `build` staat erbij.

## 5. Mapping naar het moduleplan

| Plan | EV-module |
|---|---|
| Module stelt voor, engine maakt het ene plan | `plan_ev` levert `EvPlan`; `step()` voegt het toe aan `load_kwh`; de batterij plant erop |
| Basiscomponenten delen | prijzen (`base_prices`, 15 minuten), `base_solar` (nieuw), netvermogen/fasen (nieuw gedeeld) |
| Modus per module (dry-run/advisory/auto) | alleen dry-run bestaat; het veld komt pas in stap 3 en dan standaard `dry-run` |
| Prioriteit in de load balancer | veld `ev_priority`, standaard zoals 4.5 |
| "Het minimum dat altijd mag" | minimale laadstroom 6 A en het behoud van de verplichte energie |
| Hold/hysterese | min tijd aan/uit, max wijzigingen per uur |
| HEMS kent geen merk | rollen als entity-selectors, geen `ocpp_hub` in `hems/core` |

## 6. Gefaseerd plan

**Stap 0, voorwaarden (Marks ja nodig, HA-schrijfacties, geen laderwrites)**
- DSMR-entiteiten voor stroom en vermogen per fase inschakelen.
- `CONF_EV` van HEMS omzetten naar `sensor.ocpp_hub_ed13009a_power` (of de lijst-selector uit 4.2) en `docs/hems/install.md` bijwerken.
- Beslissingen uit hoofdstuk 7.

**Stap 1, dry-run plan** (branch `feature/hems-ev-module`, geen device-calls): `ev.py` met tests (publiek gedrag: deadline gehaald als haalbaar, nooit onder 6 A of boven plafond, kwartieren goedkoopste, overschot telt als export, prijsdrempel, hysterese, onhaalbaar geeft `deadline_urgent`), `base_solar`, balancer per fase met tests, config_flow-sectie, sensoren, trace. Gedrag achter `ev_enabled = False`. Gate: HA-integratietests met de gepinde plugin 0.13.373, sync-check van de engine, AST-controle op intentcommentaar.

**Stap 2, replay en test op historische data**
- `scripts/hems_ev_replay.py` naast `hems_replay.py`: dezelfde dagen (14 tot 22 okt) met EV-lasten uit de Charge Amps-historie in de recorder (ongeveer 10 dagen, `scripts/hems_collect.py` haalt prijzen op) en de NEO-sessie van 21 okt (5,0 kWh); vergelijk kosten met "direct laden op vol vermogen" en met wat er echt gebeurde.
- Maten: kosten per geladen kWh, aantal dagen deadline gehaald, aantal kwartieren met te weinig of te veel stroom, aantal start-stops, per-fase-overschrijdingen (alleen betrouwbaar na stap 0).
- Test van de interactie: dezelfde dagen met en zonder EV in de batterijreplay; de kasuitkomst van de batterij mag door de EV niet ineenstorten.
- Meetopzet op de lader (apart, met Marks ja): stroomproefreeks 6, 8, 12, 16, 6 A tijdens een lading, pauze 0 A en herstart, reactietijd, `GetCompositeSchedule`, `duration`-profiel.

**Stap 3, niet goedgekeurd, nu niet bouwen**: advisory (sensor/melding "start nu op X A"), daarna auto met een EV-executor naar het voorbeeld van de batterij (`Execution.power_w` als enige bron, live her-controle van aangesloten/SoC/ruimte per fase vóór elke schrijfactie, `idle` terugval bij `no_soc`), schrijven via `number.set_value` op `number.ocpp_hub_ed13009a_charge_limit` en de switch, vangnet via een profiel met geldigheidsduur of `ocpp_hub.set_schedule`. Per-module modus in de opties.

## 7. Risico's en open vragen voor Mark

### 7.1 Ontdekt tijdens het onderzoek
1. **Het huisbasisverbruik raakt vervuild**: HEMS trekt het EV-vermogen af via `CONF_EV` = `sensor.charge_amps_monitor_charger_current_power`, die sinds 20 okt 14:35 dood is. De lading van 21 okt (5,0 kWh) staat dus in de belastingsgeschiedenis. Omdat het uurprofiel een mediaan over 7 dagen is, is het effect klein, maar het groeit met elke lading. Oplossing: omzetten naar de NEO-vermogenssensor (zie stap 0).
2. **De NEO staat nog op een limiet van 10 A** (number en `limit_in_effect` 10,0 sinds 21 okt 18:17, profiel `ChargePointMaxProfile`). Dat was kennelijk een test; de volgende lading is begrensd tot 10 A tot het profiel wordt gewist (`button.…clear_charge_limit`). Dit is geen HEMS-handeling: alleen melden.
3. **DSMR-stroom per fase staat uit** (hoofdstuk 3): zonder dat werkt de per-fase-balancer alleen met de conservatieve aanname.

### 7.2 Vragen
1. **Deadline**: de kia-vertrektijden (07:30 en 12:00) gebruiken, een eigen helper (`input_datetime`) of een vaste tijd in de opties? De kia-schakelaars voor gepland vertrek staan uit, dus of die tijden nog actueel zijn weet ik niet.
2. **Doel-SoC**: 80 % als dagelijkse verplichting en 100 % alleen opportunistisch? Of de kia-AC-limiet (`number.ev4_ac_charging_limit`) als bovengrens?
3. **Prioriteit bij overbelasting**: de volgorde uit 4.5 (EV urgent, boiler, batterij uit net, EV opportunistisch) goed? Mag de batterij dus altijd als eerste inleveren?
4. **Fasen**: hangt de SAJ driefasig symmetrisch aan het net? Op welke fase(n) hangen warmtepomp/boiler en de zwaarste huislasten? Wat is de grootste per-fase huisbelasting die u kent?
5. **Salderen**: de HEMS-prijsopties hebben `salderen: True`. De Nederlandse salderingsregeling eindigt volgens mijn kennis op 1 januari 2027 (te verifiëren); daarna daalt de exportprijs en wordt rechtstreeks laden op overschot veel meer waard. Dat bepaalt hoe snel `base_solar` en de overschot-term belangrijk worden.
6. **Raedian-backend**: moet HEMS-gestuurd laden de sessies bij Raedian blijven aanleveren? Dat doet de mirror, de reden dat de backend alleen leest. Controle: staat de mirror op `connected` tijdens een gestuurde lading, en blijft de sessie bij Raedian kloppen als HEMS de stroom wijzigt?
7. **Home Balance en Solar Charging van de NEO**: in de Modbus/EMS-stand staan ze uit (installatiehandleiding); voor de OCPP-route is niet bevestigd dat de laadstroom in de Install-app op "vast" staat en load management uit. Wat staat er? Zo niet, dan bestrijden de lader en HEMS elkaar.
8. **Vangnet**: welk gedrag wilt u als HEMS wegvalt tijdens een lading: laatste setpoint laten staan (gevaarlijk op 16 A), terug naar 6 A, of pauzeren? Dit stuurt de eis aan ocpp-hub (geldigheidsduur) en de EV-executor.

### 7.3 Risico's
| Risico | Wat ervan te verwachten is | Dempen |
|---|---|---|
| NEO honoreert `SetChargingProfile` niet dynamisch | planner zonder effect | stroomproefreeks vóór stap 3; dry-run is onschuldig |
| Pauze op 0 A werkt niet of de auto beëindigt de sessie | eigen switch stop/start nodig, extra sessies bij Raedian | proef; dan liever 6 A dan 0 A als minimum |
| Setpoint blijft staan als HEMS of HA wegvalt | 16 A + huispiek = lange overbelasting | geldigheidsduur-profiel, dagschema als vangnet, plafond in ocpp-hub op 16 A houden |
| kia_uvo-SoC is vertraagd of springt | te veel of te weinig energie gepland | SoC-schatting uit de lader-kWh, deadline met veiligheidsmarge, `stale_soc` zoals bij de batterij |
| Per-fase-meting ontbreekt of heeft geen teken | te voorzichtig of onveilig | conservatieve terugval, meting in stap 0 |
| Batterij en EV vechten om de goedkoopste kwartieren | beide planningen mislukken in de uitvoering | plafond in `Slot` en prioriteit, zie 4.5 |
| Veel HA-herstarts (13 op 18 en 19 okt) | EV-executor weet niet wat er al verstuurd is | idempotente setpoints, herstel binnen 60 s zoals de planner; de hub-number toont na herstart niets |
| `EvState` uit twee integraties (kia en ocpp_hub) loopt uit de pas | tegenstrijdige plug- of laadstatus | ocpp_hub leidend, kia alleen voor SoC en capaciteit |

## 8. Niet geverifieerd

- Of de NEO een limiet tijdens een lopende lading wijzigt, hoe snel, en of 6 tot 16 A en pauze op 0 A werken; of `duration` en `GetCompositeSchedule` werken; of het dagschema herhaalt (roadmap zegt zelf: onbewezen).
- De eenheid van `sensor.ev4_ev_battery_capacity` (aangenomen kJ, 81,4 kWh), de betekenis van `sensor.ev4_ev_charging_current_limit`, en de verversfrequentie van kia_uvo.
- Of de kia-vertrektijden (07:30, 12:00) actueel zijn.
- Welke DSMR-entiteiten per fase er precies zijn (L2 en L3, vermogen negatief), hun updatesnelheid en teken.
- Of de SAJ driefasig symmetrisch laadt en op welke fase de huislasten hangen.
- De werkelijke instelling van de Install-app (vaste laadstroom, load management) en wat Raedian's cloud met mijn limiet doet.
- Het laadrendement AC naar accu van de EV4 (aangenomen 0,90 tot 0,92).
- De salderingsdatum 1 januari 2027 (uit mijn kennis, niet in de repo of via een bron gecontroleerd).
- Het gedrag bij een volledige HA-herstart (alleen een herlading is gemeten: 14 s).
- De monitoringrapporten van 21 en 22 okt: de bestanden bestaan niet in `docs/hems/observations/monitoring/` (laatste dagrapport 20 okt, weekoverzicht van 21 okt).

## 9. Bij de start van het bouwen bijwerken

- `hems/AGENTS.md` en `docs/hems/intake-decisions.md` zeggen nog "EV buiten beschouwing"; omzetten naar de besluiten van Mark uit hoofdstuk 7.
- `docs/hems/install.md`: de rij "EV-vermogen" naar `sensor.ocpp_hub_ed13009a_power`, de nieuwe sectie `module_ev` en de sensoren.
- `hems/core/hems/contracts.py`: EV-poort. `scripts/sync_hems_core.py` na elke kernwijziging.
- Geheugen `project_hems-module-plan.md`: de EV-module is niet meer "Charge Amps, niet gebouwd, buiten beschouwing".
