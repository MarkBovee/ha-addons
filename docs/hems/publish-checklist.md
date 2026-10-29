# HEMS publiceren: checklist (29 okt 2026)

Mark (29 okt): HEMS gaat naar een eigen repository als we zover zijn, net als de OCPP-hub (`MarkBovee/ocpp-hub`). De Marketplace
(HACS) verwacht één integratie per repository, met `custom_components/hems/` in de root.

## Al klaar
- `custom_components/hems/brand/`: icon, icon@2x, logo, logo@2x en dark-varianten (HA 2026.3+); bron in `docs/hems/brand/*.svg`,
  renderen met `scripts/build_hems_brand.sh`. Geen HA-merkbeeld (geen huis).
- `manifest.json`: `version` (0.2.0), `documentation`, `issue_tracker`, `codeowners`, `config_flow`, `integration_type`, `iot_class`.
- `translations/en.json` volledig; alleen Engels (geen `nl.json`).
- `hems/README.md` (Engels, voor gebruikers) en `hems/CHANGELOG.md`.
- MIT-licentie in de root.

## Bij de verhuizing naar de eigen repo
1. Nieuwe repo `MarkBovee/hems` met de geschiedenis van `custom_components/hems`, `hems/core`, `hems/tests` en `tests/hems_ha`
   (`git filter-repo --path ...`), zodat de commits behouden blijven.
2. In de root: `README.md` (uit `hems/README.md`, beeldpad naar `custom_components/hems/brand/`), `LICENSE`, `CHANGELOG.md` en
   `hacs.json`:
   ```json
   {"name": "HEMS", "homeassistant": "2026.3.0", "render_readme": true}
   ```
3. `manifest.json`: `documentation` en `issue_tracker` naar de nieuwe repo.
4. CI: de core-tests en de HA-tests (plugin 0.13.375), en de HACS- en hassfest-validatie (`hacs/action`, `home-assistant/actions/hassfest`).
5. Release met tag `v0.2.0` gelijk aan `version` in het manifest; de Marketplace leest de brand-afbeeldingen uit de laatste release.
6. Repo-specifieke delen niet meenemen of algemeen maken: `hems/deploy.py` (eigen server), `scripts/hems_*` met entiteit-id's van
   deze installatie, `docs/hems/observations/`.
7. Daarna in `ha-addons`: HEMS verwijderen en naar de nieuwe repo verwijzen.

## Nog open voor een eerste publieke versie
- Schrijven naar apparaten staat op slot; een publieke release vóór fase 4 is een planner met advies.
- De SAJ-schrijver is SAJ-specifiek; andere omvormers krijgen alleen het plan.
