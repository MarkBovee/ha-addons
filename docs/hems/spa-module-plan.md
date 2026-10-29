# Spa-module (plan, 29 okt 2026)

Mark heeft op 29 okt een spa geïnstalleerd; de Balboa bwa-wifimodule (50350) komt later. Deze module wordt nu voorbereid, zodat
de spa meedoet zodra de integratie er is.

## Bestemming

HEMS houdt de spa op temperatuur en schuift het bijwarmen naar goedkope kwartieren en PV-overschot. Bij een volle aansluiting
wijkt de spa als eerste. Eerst in dry-run en advisory, met hetzelfde slot als batterij en boiler.

## Beslissingen (Mark, 29 okt)

| Beslissing | Inhoud |
| --- | --- |
| Integratie | Balboa Spa Client (HA core, lokaal). HEMS werkt op rollen, dus een andere spa-integratie met een climate-entiteit werkt ook |
| Aansluiting | 1 fase, ongeveer 3 kW heater. De fase (L1/L2/L3) en het vermogen zijn instellingen |
| Doel | Altijd op temperatuur, goedkoop bijwarmen: een comforttemperatuur met een band eromheen. Bij goedkope stroom of PV-overschot mag het water tot `comfort + boven` gaan, bij dure stroom mag het zakken tot `comfort − onder`, en nooit lager |
| Prioriteit | Huis > boiler > EV > spa. Bij een volle fase pauzeert de spa-heater eerst |

## Wat de Balboa-integratie levert (HA core)

- `climate`: huidige en doeltemperatuur. `hvac_mode` `heat` is Ready, `off` is Rest. Presets `ready`, `rest`, `ready_in_rest`.
  `hvac_action` `heating`/`idle`.
- `select` temperatuurbereik (high/low), `time` voor de filtercycli, `switch` filtercyclus 2, `fan` voor de pompen, `light`.
- Geen vermogensmeting. HEMS schat het verbruik als `hvac_action == heating` maal het vermogen van de heater, tenzij er een
  vermogensrol is (bijvoorbeeld een kWh-meter in de groep).

## Model

- **Opwarmen:** `heat_rate_c_h` (instelling, standaard 2 °C/u voor ongeveer 1300 l en 3 kW). Later te leren uit de metingen.
- **Afkoelen:** `cool_rate_c_h` als functie van het verschil met de buitentemperatuur, die HEMS al heeft:
  `k · (T_water − T_buiten)`, met `k` als instelling (standaard 0,02/u) en later geleerd.
- **Plan:** een kleine DP per kwartier op een temperatuurraster van 0,25 °C. De beslissing per kwartier is heater aan of uit, en
  de kosten zijn de importprijs, of de exportprijs bij PV-overschot. De band moet altijd gehaald worden. Uitkomst: per kwartier
  aan/uit, de verwachte temperatuur en de kWh. Die kWh gaan in de verbruiksprognose, zoals bij de boiler.
- **Uitvoeren:** via de doeltemperatuur van de climate-entiteit. Bijwarmen is `comfort + boven`, laten zakken `comfort − onder`,
  en verder `comfort`. HEMS zet de spa nooit uit (Rest). De spa-elektronica blijft dus zelf beschermen tegen vorst en te heet water.

## Verdelen over de fasen

`hems.balancer.allocate_phases` kan dit al: een `PhaseLoad` met `share` op één fase, bijvoorbeeld `(0, 1, 0)` voor L2, de
laagste prioriteit en `min_a` gelijk aan de stroom van de heater (aan of uit). Krijgt de spa die stroom niet, dan schrijft HEMS
`comfort − onder` (pauze) en houdt de rest van het plan aan. De EV gaat vóór de spa.

## Werk in plakken

| # | Plak | Bewijs |
| --- | --- | --- |
| 1 | Rollen `spa_climate_entity` (climate), optioneel `spa_power_entity` (sensor, W), en de instellingen (aan/uit, fase, kW, comfort, boven, onder, opwarm- en afkoelsnelheid) | config-flow-test |
| 2 | Engine `hems.spa`: model en DP-plan, de band altijd gehaald, goedkoop vooraf bijwarmen | tests: koude nacht, goedkope middag, PV-overschot, band onhaalbaar |
| 3 | De spa als load in de verbruiksprognose en in `allocate_phases` met de laagste prioriteit | test: EV en spa op één fase, de spa wijkt |
| 4 | Advisory: `sensor.hems_spa_target` (doeltemperatuur, reden, plan) en een tegel op Devices | HA-test |
| 5 | Schrijver achter het slot (`climate.set_temperature`) | test met een nep-climate; geen aanroep in dry-run |
| 6 | Als de module er is: rol zetten, opwarm- en afkoelsnelheid meten, advisory een paar dagen | in het echte paneel |

## Voortgang (29 okt 2026, branch `feature/hems-spa`)

Plak 1 t/m 5 gebouwd, de module staat standaard uit:
- Rollen `spa_climate_entity` en `spa_power_entity`, plus het onderdeel "Module: spa" in de instellingen (fase L1/L2/L3, kW, comfort, boven, onder, opwarm- en afkoelsnelheid) en `select.hems_spa_mode`.
- `hems.spa.plan_spa`: DP op 0,05 °C. Binnen de band moet elk kwartier ook binnen de band eindigen; onder de band verwarmt hij altijd; PV-overschot telt tegen de exportprijs. De kWh gaan na de EV in de verbruiksprognose.
- `Coordinator.spa_allowed`: de stroom per fase van de meter, min die van de auto en van de spa zelf, door `allocate_phases` met EV vóór spa. Zonder meterwaarden houdt HEMS de spa niet tegen.
- `sensor.hems_spa_target` (doel, verwarmen ja/nee, reden, haalbaarheid en de kwartieren vooruit).
- Schrijver `climate.set_temperature` (alleen bij een verschil, nooit de modus), achter `WRITE_UNLOCKED` en auto.

Als de wifi-module er is: de Balboa-integratie toevoegen, `spa_climate_entity` zetten, de module aanzetten met de juiste fase en het juiste vermogen, en een paar dagen de opwarm- en afkoelsnelheid naast de meting leggen.

## Open (later, met de spa erbij)

- Welke fase (L1/L2/L3), en het werkelijke vermogen. Ook of de pompen en de heater samen meer dan 16 A trekken.
- Of de spa "Ready" moet blijven, of dat HEMS 's nachts naar "Rest" mag. Voorlopig nooit Rest.
- De filtercycli laten we aan de spa over. Ze naar goedkope uren verplaatsen kan later via de `time`-entiteiten.
