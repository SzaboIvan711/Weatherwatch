## Was

<Eine bis drei Zeilen: was ändert dieser PR? Nicht den Diff nacherzählen.>

## Warum

<Zwei bis drei Sätze: welches Problem / welcher Meilenstein, welche Alternative wurde verworfen?>

## Art der Änderung

- [ ] feat – neue Funktion
- [ ] fix – Fehlerbehebung
- [ ] ci / build – Pipeline, Container, Infrastruktur
- [ ] docs – Dokumentation
- [ ] chore / refactor / test

## Selbstprüfung

- [ ] Eigenen Diff auf GitHub vollständig gelesen.
- [ ] `make check` lokal grün (ruff, Format, pytest, Coverage ≥ 80 %).
- [ ] CI-Check **CI passed** ist grün.
- [ ] Neue oder geänderte Logik ist durch Tests abgedeckt – oder Begründung: <…>
- [ ] Dokumentation angepasst (README, DEPLOYMENT, MONITORING, ADR) – oder nicht betroffen.
- [ ] Keine Secrets, Passwörter, Tokens oder Keys im Diff.

## Wie getestet?

<Konkrete Befehle und Ergebnisse, z. B. `docker compose up --build`, `curl localhost:8000/health` → 200, `kubectl get pods` → 2/2 Running.>

## Bewusst offen

<Was bleibt absichtlich für einen späteren PR? „nichts“, falls nichts.>
