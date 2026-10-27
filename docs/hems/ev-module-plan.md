# EV-module: plan en beslissingen (intake, 27 okt 2026)

Statusdocument van de intake; het onderzoek staat in `ev-module-research.md`. Dit bestand indexeert beslissingen en wordt na elke ronde bijgewerkt.

## Bestemming

Een schakelbare EV-module in HEMS die als dry-run per kwartier een laadplan en een setpoint voorstelt (deadline, prijsdrempel, PV-overschot als termen van één planner), met de basiscomponent `base_solar` en een balancer per fase. Geen schrijfacties naar de lader of naar HA.

## Beslissingen tot nu toe

- **Deadline = schema.** Een weekschema van dag + tijd (voorbeeld: maandag 07:30 en donderdag 07:30), geen vaste dagelijkse tijd en niet uit de kia-cloud. (Mark, ronde 1)
- **Doel-SoC: 80 % verplicht, 100 % opportunistisch**, beide instelbaar. (Mark, ronde 1)
- **Prioriteit bij overbelasting:** EV met urgente deadline, boiler, batterij laden uit net, EV opportunistisch; per module later instelbaar. (Mark, ronde 1)
- **Scope stap 1:** EV-planner + `base_solar` + balancer per fase, op een eigen branch, alleen dry-run. (Mark, ronde 1)
- **Zonder deadline: alleen opportunistisch**, plus een handmatige **override "forceer laden"** voor als je echt moet laden terwijl de prijzen slecht zijn. Geen vloer-SoC. (Mark, ronde 2)
- **Prijsdrempel = absoluut bedrag** (EUR/kWh, effectieve prijs). (Mark, ronde 2)
- **Salderen stopt automatisch op een instelbare datum** (standaard 2027-01-01), en HEMS rekent daarna met de echte exportprijs. Opgezocht (Zonneplan, 27 okt 2026): erna geen energiebelasting-teruggave en een kale prijs zonder btw; Zonneplan betaalt marktprijs + 0,02 EUR/kWh, met 10 % zonnebonus bij daglicht en positieve prijs (tot 7500 kWh/jaar). Wettelijk minimum tot 2030: 50 % van het kale leveringstarief. Dit verandert ook de verkoopeconomie van de batterij en is geen EV-werk. Niet bevestigd: of btw nog meespeelt; check het contract. (Mark, ronde 2)
- **Schema-invoer:** zeven optionele tijdvelden (maandag tot zondag) in sectie `module_ev`; leeg = geen deadline die dag. (Mark, ronde 3)
- **Override "forceer laden":** een HEMS-schakelaar (nieuw `switch`-platform); aan = zo snel mogelijk laden tot de verplichte doel-SoC, uit bij bereiken of loskoppelen; de fasegrens blijft gelden. (Mark, ronde 3)
- **Salderen-datum rijdt mee met EV stap 1** (Mark koos dit boven een eigen branch). Dempen: aparte commits en een eigen test op de prijzen voor en na de datum, zodat de batterijgevolgen los te beoordelen zijn. (Mark, ronde 3)
- **Eerder vastgelegd** (onderzoek, 22 okt): één planner met drie geprijsde termen; EV plant vóór de batterij en komt als vaste last in `load_kwh`; plafond op laden uit het net per kwartier in `Slot`; ocpp_hub leidend voor plug- en laadstatus, kia alleen voor SoC en capaciteit.
- **Uitgevoerd op 22 okt met Marks ja:** DSMR-stroom en -vermogen per fase ingeschakeld; `CONF_EV` staat op `sensor.ocpp_hub_ed13009a_power` (reconfigure-stap, commit `cb3d4ce`).

## Aannames (laag risico, goedkoop terug te draaien)

- De prijsdrempel is een instelling met een voorzichtige standaard; het bedrag geeft Mark. Wat het tegenspreekt: een eerste replay waarin de EV bijna nooit of altijd laadt.
- De SAJ laadt driefasig symmetrisch en de EV hangt driefasig; per-fase-aandelen van de boiler en de huislasten komen uit de gemeten stroom per fase, niet uit een aanname. Wat het tegenspreekt: een per-fase-meting die een fase structureel zwaarder laat zien tijdens batterijladen.
- Hysterese-standaard: minimaal 10 minuten aan en uit, stroomwijziging pas bij 1 A verschil en hoogstens eens per kwartier. Wat het tegenspreekt: veel start-stops in de replay.
- Laadrendement AC naar accu 0,90.

## Nog niet scherp

- Laadrendement AC naar accu van de EV4 meten (lader-kWh tegen SoC-sprong); tot dan 0,90.
- Betekenis van `sensor.ev4_ev_charging_current_limit` en de eenheid van `sensor.ev4_ev_battery_capacity`.

## Later (vóór stap 3, niet nu nodig)

- Vangnet als HEMS wegvalt tijdens een lading (laatste setpoint, 6 A of pauze) en de eis aan ocpp-hub voor een profiel met geldigheidsduur.
- Install-app van de NEO: laadstroom op vast, load management uit.
- Raedian: blijft de mirror `connected` en kloppen de sessies als HEMS de stroom wijzigt.
- Stroomproefreeks op de lader (6, 8, 12, 16, 6 A, pauze op 0 A, `GetCompositeSchedule`, `duration`).

## Buiten scope

- Advisory en auto (schrijven naar de lader): niet goedgekeurd.
- Per-array PV-model (tilt, azimut) en curtailment.
- Een gezamenlijke DP voor batterij en EV: te traag in zuiver Python, vervangen door sequentieel plannen.

Open questions: none. Gedeeld begrip bevestigd door Mark op 27 okt 2026 (ronde 4); bouwen op branch `feature/hems-ev-module`, alleen dry-run, niet pushen of deployen zonder ja.
