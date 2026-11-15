# WeatherWatch

Wetter-App für Chur (aktuelle Werte und Vorhersage) als Träger einer
vollständigen DevOps-Kette – Abschlussprojekt im Modul CDS212.

**Status:** im Aufbau. Arbeitsweise: GitHub Flow, siehe
[CONTRIBUTING.md](CONTRIBUTING.md).

## Geplanter Umfang (eingefroren)

- `GET /api/weather` – aktuelle Werte je Ort (Standard: Chur)
- `GET /api/forecast` – Tagesvorhersage
- `GET /api/history` – gespeicherte Abrufe
- `GET /health`, `/ready`, `/metrics` – Betrieb

Externe Quelle: Open-Meteo, 15-Minuten-Cache, PostgreSQL.
