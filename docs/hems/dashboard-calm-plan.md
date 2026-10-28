# HEMS-dashboard: rustiger ontwerp (plan, 28 okt 2026)

Mark vond het paneel te druk ("het kan veel rustiger en er kan veel meer gegroepeerd worden"). Dit plan vervangt de indeling van de huidige
`hems-panel.js` (9 tabs). Het ontwerp: https://claude.ai/artifact/GCQXjJawNXKxdmpSEQykij (Today, wall tablet, Devices, Insights).

## Wat nu te druk is
- 9 tabs, waarvan Batterij, Auto, Boiler en Net elk een eigen pagina met dezelfde soort tegels zijn.
- Een statusbalk met vier gestippelde labels plus een regel met vijf statuspunten op elke pagina.
- Elk blok heeft een rand, een hoofdletter-label en 3 tot 6 tegels; alles weegt even zwaar.
- De tijdlijn heeft vijf losse banen (prijs, plan, SoC, zon/huis, apparaten) met elk een eigen as.
- Instellingen in woorden, rollen en wapenen staan tussen de dagelijkse informatie.

## Nieuwe indeling: vier plekken en een tandwiel
| Plek | Inhoud | Vervangt |
|---|---|---|
| **Today** | Eén zin wat HEMS zou doen en waarom; drie live getallen (zon, net, batterij %); één grafiek (prijs als staven, SoC als lijn, laad- en verkoopvensters als band eronder); één agenda "Coming up" voor alle apparaten; geld vandaag | Nu, delen van Plan en Prijzen |
| **Plan** | De volledige tijdlijn (8/24/48 u) met het waarom per kwartier, de vensters als lijst en wat er sinds het vorige plan is veranderd | Plan |
| **Devices** | Per apparaat één rij: wat het doet in een zin, de kerncijfers, de eigen bediening (modus, geforceerd laden). Details klappen uit. Netaansluiting klein onderaan, want die is een grens, geen apparaat | Batterij, Auto, Boiler, Net |
| **Insights** | Eerst de vraag "levert het iets op" (totaal en per dag), dan drie rustige blokken: verwachtingen, prijzen, vergelijking met de oude manager | Leren, Prijzen |
| **Tandwiel** (paneel van rechts) | Wapenen, alles naar dry-run, rollen, instellingen in woorden, link naar HEMS-instellingen | Regie |

Status wordt één pil ("Dry-run · all data fresh"); pas bij een probleem kleurt hij en klapt de uitleg uit. Alarmen blijven een balk bovenaan, maar alleen als er een aan staat.

## Wandtablet (kiosk)
Eén scherm zonder tabs: groot woord ("Holding"), twee tijden, drie grote getallen, de grafiek, en één regel "Next". Geen tabellen, geen bediening.

## Visuele regels
- Minder randen: vlakken onderscheiden zich door een iets lichtere achtergrond (`#161a1f` op `#111418`), geen kaders om alles.
- Eén lettertype voor tekst (IBM Plex Sans) en één voor getallen (IBM Plex Mono); geen hoofdletter-labels meer.
- Kleur alleen voor betekenis: blauw = laden/goedkoop, oranje = verkopen/duur, groen = ok/winst. Grijs voor de rest.
- Ruimte: 40 px marge, 36–40 px tussen secties; tekst 15 px, verdict 36 px (kiosk 56 px).
- Dry-run zie je aan de statuspil en de modusknop per apparaat, niet aan arcering op elk element.

## Uitvoering (na akkoord op het ontwerp)
1. Navigatie naar vier plekken plus tandwiel; oude hashes blijven via aliassen werken.
2. Today bouwen (verdict, live, gecombineerde grafiek, agenda, geld); de agenda voegt `windows`, `heating` en de EV-blokken samen.
3. Devices als rijen met uitklapbare details; Insights samenvoegen.
4. Tandwielpaneel voor Regie; statuspil met uitklap.
5. Kiosk als één scherm.
6. Lichte thema afleiden van dezelfde tokens; testen op 390, 893 en 1280 px.

De payload en de websocket blijven gelijk; dit is alleen frontend (`hems-panel.js`).

## Open
- Plan-pagina is nog niet getekend: die blijft grotendeels de huidige tijdlijn, maar met één gecombineerde grafiek in plaats van vijf banen. Eerst Marks reactie op Today.
- Licht thema: nog niet getekend.
