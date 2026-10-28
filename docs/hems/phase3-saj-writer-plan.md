# Fase 3: de SAJ-schrijflaag (plan, 28 okt 2026)

Branch: `feature/hems-saj-writer`, vanaf `feature/hems-dashboard-panel` (`a01e3f4`). Hoort bij `live-transition-plan.md` §4–7.

## Bestemming

HEMS kan het batterijplan omzetten in SAJ-tijdsloten en die schrijven volgens het protocol van battery-api (§4.2). Dat is
bewezen met een nepdienst in de tests. **Advisory** publiceert het schema dat HEMS zou schrijven en het verschil met wat de SAJ
nu heeft. **Auto blijft op slot**: er wordt in fase 3 niets naar de omvormer geschreven. De watchdog ligt klaar als
HA-automation. Fase 4 (de begeleide advisory-dag en daarna een auto-dag) opent het slot, na Marks ja.

## Beslissingen

| Beslissing | Inhoud | Bron |
| --- | --- | --- |
| Eindpunt | Schrijflaag af en getest; advisory zichtbaar; auto op slot | Mark, 28 okt |
| Horizon | Elk kwartier opnieuw opgebouwd uit het plan van nu tot nu+24 u; alleen afwijkende velden schrijven | Mark, 28 okt |
| Twee grenzen | De reserve (nu 30 %) is de **verkoopgrens**: een verkoopslot stopt daar en HEMS kort het in. Daaronder gaat de batterij naar **dynamisch**: het huis dekken met 0 W op de meter, tot `hard_min` (5 %, de SAJ-ontlaaddiepte). Zo werkt battery-manager ook (`conservative_soc`, daarna adaptive tot `min_soc`). Risico bij uitval van HEMS: een verkoopslot loopt door tot de watchdog ingrijpt (30 min, bij 8 kW tot ongeveer 4 kWh onder de grens) | Mark, 28 okt |
| Reserve volgt het verbruik | Reserve = verwacht huisverbruik min PV (P90-band) van het einde van een verkoop tot het volgende geplande laadmoment of de ochtendzon, plus `hard_min`; begrensd door een instelbaar minimum (30 %) en maximum (bijv. 60 %). In de winter stijgt hij vanzelf naar 40 à 50 %. Battery-manager doet dit grover via de temperatuur (minder verkooputen bij kou) | Mark, 28 okt |
| Buiten vensters altijd 0 W | Buiten laad- en verkoopvensters dekt de batterij het huis (0 W op de meter); "vasthouden" (batterij uit terwijl het huis importeert) bestaat niet meer. In de planner wordt `idle` zelfverbruik, net als de baseline van Insights | Mark, 28 okt |
| Eigen regelaar (dynamisch) | De SAJ-zelfverbruikmodus zit ongeveer 500 W naast de meter, daarom regelt HEMS zelf, zoals `_calculate_adaptive_power` van battery-manager: elke minuut doel = huidig vermogen + P1-netvermogen, reageren vanaf 50 W, afronden op 100 W, onder `min_discharge_power` naar 0, schrijven pas bij ≥ 100 W verschil. Dat gaat via één vast ontlaadslot rond het lopende kwartier; er blijven dus 6 ontlaadsloten voor verkopen. PV-overschot: geen ontlaadslot, zodat de SAJ zelf laadt | Mark, 28 okt |
| Watchdog | Zonder voorwaarde op een HEMS-entiteit (die is `unavailable` als HEMS weg is); pas installeren bij de overdracht, als battery-manager gestopt is (Mark, 28 okt: BM verdwijnt). HA-automation buiten HEMS: `sensor.hems_last_cycle` ouder dan 30 min, `sensor.hems_status` 30 min niet `ok`, of HEMS `unavailable` → alle sloten leeg, bitmaskers 0, modus Self-consumption, melding | Mark, 28 okt |
| Entiteiten | Zoals battery-api (`ModbusEntityDiscovery`): vaste standaardnamen van `saj_h2_modbus` met aliassen, controle bij de start, optioneel per sleutel te overschrijven. Lezen slot 1 `sensor.saj_charge_start_time`, slot n `sensor.saj_charge_<n>_…`; schrijven `text.saj_charge<n>_start_time_time`, `number.saj_charge<n>_power_percent_input`, `number.saj_charge<n>_day_mask_input` | Mark, 28 okt: "kijk naar battery-api" |
| Advisory | `sensor.hems_battery_schedule` (sloten als attributen, verschil met de SAJ) en een blok "Would write" op Devices → Battery; geen meldingen | Mark, 28 okt |
| Samenvoegen | In de slotbouwer, niet in de planner: een gat van hooguit 2 idle-kwartieren vullen als dat minder dan € 0,05 per uitgespaard slot kost; altijd samenvoegen (goedkoopste gat eerst) als er anders meer dan 7 nodig zijn; kosten loggen | `insights-findings.md` §1 |

## Aannames (goedkoop terug te draaien)

- **Vermogen per slot:** het gemiddelde AC-vermogen van het blok, als percentage van 8000 W (`modbus_inverter_power_w`), afgerond zoals battery-api. Een vermogen van 0 % wordt geen slot. Fout als de SAJ een ander referentievermogen gebruikt; dat blijkt uit de terugmelding.
- **Over middernacht:** een blok dat over 00:00 loopt, wordt gesplitst in twee sloten (tot 23:59 en vanaf 00:00). Of de SAJ een eindtijd vóór de starttijd aanvaardt, is niet bevestigd (§8), dus dit is de veilige keuze.
- **Volgorde van schrijven:** per slot de velden (start, eind, vermogen, dagmasker 127; ongebruikt: 00:00, 00:00, 0 %, masker 0), dan de bitmaskers, dan de modus (Time-of-use bij minstens één slot, anders Self-consumption), dan de terugmelding via de uitleesentiteiten met beperkte pogingen. Bij een verschil geldt het schrijven als mislukt en zet HEMS een alarm.
- **Schrijfbudget:** hooguit één schrijfronde per cyclus, en geen nieuwe ronde als het schema gelijk is aan het vorige. Elke schrijfactie wordt een `write`-event in het spoor.
- **Nooit schrijven** bij een status anders dan `ok`, bij `no_soc`/`stale`, in de eerste cyclus na een start (geen oud schema herhalen) of zolang de oude battery manager nog verversende sensoren heeft. Dat laatste is pas in fase 4 relevant; de controle wordt nu al gebouwd.
- **Wissen bij stoppen:** bij het ontladen of verwijderen van de integratie leegt HEMS zijn sloten, maar alleen in auto. In fase 3 is dat dus nog niet actief.
- **Test-plugin:** `pytest-homeassistant-custom-component` naar 0.13.375 (pint HA 2026.10.4), in de venv en in `hems/AGENTS.md`.

## Werk in plakken (elk eindigt groen)

| # | Plak | Bestanden | Niveau | Bewijs |
| --- | --- | --- | --- | --- |
| 0a | **Planner: twee grenzen en `idle` = zelfverbruik.** De vloer per kwartier remt alleen export; het huis dekken mag tot `hard_min`. Insights vergelijkt daarna weer gelijk (BM adaptive = HEMS idle) | `battery.py`, `rolling.py`, engine-kopie | diep | bestaande tests bijgewerkt, nieuwe test "na de verkoop dekt de batterij het huis onder de 30 %", replay vanaf 17 okt voor en na |
| 0b | **Reserve uit het verwachte verbruik**, via het bestaande `Slot.reserve_soc` | `battery.py` of nieuw `reserve.py`, opties min/max | standaard | test winter/zomer op de vorm van de vorige week; replay: wat kost of levert het op |
| 1 | Test-plugin 0.13.375 | venv, `hems/AGENTS.md` | licht | de bestaande 254 + 65 tests groen op de nieuwe pin |
| 2 | **Slotbouwer** (puur, engine): plan → sloten voor 24 u, samenvoegregel, splitsen bij middernacht, 7-grens, vermogen in % | `hems/core/hems/saj_slots.py`, tests | standaard | tests op de echte plannen van 26 en 28 okt (uit `plans.jsonl` als fixture): aantal sloten, kosten van samenvoegen, nooit meer dan 7 |
| 3 | **SAJ-schrijver** (HA-kant): ontdekking van de entiteiten, verschil met de huidige staat, schrijven via `text.set_value` en `number.set_value`, terugmelding, mislukking als alarm | `custom_components/hems/saj.py`, tests | diep | tests met een **nepdienst** (geregistreerde `text`/`number`-services die de staat bijwerken, en één die faalt of een afwijking teruggeeft): idempotent, alleen verschillen, volgorde, verificatie, geen schrijven in dry-run/advisory |
| 3b | **Regelaar (dynamisch)**: P1-meter elke minuut, het algoritme van battery-manager, één ontlaadslot, schrijfbudget van één vermogenschrijving per minuut, alleen in auto | `custom_components/hems/grid_follow.py`, tests | diep | tests met de nepdienst en een nep-meter die 500 W afwijkt: komt binnen 50 W, schrijft niet bij ruis, stopt bij PV-overschot en bij een laad- of verkoopslot |
| 4 | **Modus en slot** | `coordinator.py`, `select.py` | standaard | test: auto is niet te kiezen; advisory berekent wel, schrijft niet; status anders dan `ok` geeft geen schema |
| 5 | **Advisory zichtbaar**: `sensor.hems_battery_schedule` en "Would write" op Devices | `sensor.py`, `dashboard.py`, `hems-panel.js` | standaard | HA-test op de sensor; controle in het echte paneel na deploy |
| 6 | **Watchdog** | `hems/watchdog/hems_saj_watchdog.yaml` (blueprint of automation), `docs/hems/install.md` | standaard | YAML gevalideerd met `ha_config_set_automation` in een droge controle; installatie pas na Marks ja |
| 7 | Docs en plan bijwerken | `live-transition-plan.md`, `hems/AGENTS.md`, `install.md` | licht | — |

**Testnaden:** (a) de pure engine (planner en slotbouwer), met plannen als invoer; (b) de HA-integratie met de nepdienst, vanaf de coordinatorcyclus en de regelaar.
Andere naden komen er niet bij.

## Gates

- Na plak 3b en 6, op de definitieve diff: **onafhankelijke review** (`ask-reviewer`, P0/P1) en **audit** (`ask-auditor`) van de
  schrijflaag. Vrijgave-gevoelig: de review door de implementer zelf telt niet.
- Gate cost: core- en HA-tests plus de deploy in dry-run, review op standaardniveau, audit op diep niveau (schrijfpad, verdeling
  van de vloer en de watchdog zijn invarianten die over modules heen lopen), ongeveer 2 agentruns.

## Buiten fase 3

- Echt schrijven, de overdracht van BM naar HEMS en de proefdagen: fase 4.
- Passieve modus: pas na meting (§4.3).
- Telemetrierollen naar `sensor.saj_*` omzetten: na het uitfaseren van battery-api.
- Boiler en EV live: fase 5.

Open questions: none. Aannames: zie hierboven.
