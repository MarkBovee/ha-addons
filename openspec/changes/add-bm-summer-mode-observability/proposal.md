## Why
Battery Manager mist momenteel een expliciet signaal voor dagen waarop de laagste stroomprijzen midden op de dag liggen. Dit maakt het lastig om summer-gedrag te herkennen en veilig te observeren voordat strategie-aanpassingen worden geactiveerd.

## What Changes
- Add summer-mode detectie op basis van prijsprofiel van vandaag:
  - top-N goedkoopste perioden,
  - majority in een configureerbaar middagvenster (standaard 10:00-16:00).
- Add summer-mode zichtbaarheid in bestaande status/mode/schedule-uitvoer.
- Add dagstartmelding met icoon `🌞 Nieuw dagschema (Summer)` wanneer een nieuw dagschema wordt gepubliceerd en summer-mode actief is.
- Add configuratie-opties voor enable/disable, venster en top-N selectie.
- Keep gedrag bewust niet-invasief in deze fase: geen wijziging aan laad/ontlaad selectie of power dispatch.

## Impact
- Affected specs: `battery-strategy`
- Affected code:
  - `battery-manager/app/price_analyzer.py`
  - `battery-manager/app/main.py`
  - `battery-manager/app/status_reporter.py`
  - `battery-manager/config.yaml`
  - `battery-manager/README.md`
  - `battery-manager/CHANGELOG.md`
  - `battery-manager/Tests/test_price_analyzer.py`
  - `battery-manager/Tests/test_status_reporter.py`
