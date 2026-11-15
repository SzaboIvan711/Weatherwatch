# Mitarbeit im Projekt

Diese Regeln gelten für dieses Repository. Das Projekt ist eine Einzelarbeit –
die Regeln sind trotzdem verbindlich: Sie sind die Disziplin, die im Team
selbstverständlich sein muss.

## Branching-Strategie: GitHub Flow

`main` ist **immer deploybar** – jeder Commit auf `main` wird nach grüner CI
automatisch auf Render ausgeliefert. Direkt auf `main` wird **nie** gepusht.

Branch Protection Rule für `main` (*Settings → Branches*):

- *Require a pull request before merging*
- *Require status checks to pass before merging* → Check **`CI passed`**
- *Require branches to be up to date before merging*
- *Do not allow bypassing the above settings*
- Force-Pushes und Löschen von `main` nicht erlaubt

Ablauf für jede Änderung:

1. Kurzlebigen Branch von einem aktuellen `main` abzweigen.
2. Klein und thematisch geschlossen committen, pushen, **Pull Request** öffnen.
3. Den eigenen Diff **auf GitHub** lesen und die Selbstprüfung in der
   PR-Beschreibung ausfüllen (Vorlage wird automatisch eingefügt).
4. Warten, bis **`CI passed`** grün ist. Rot blockiert den Merge.
5. Mergen (*Squash and merge* oder *Create a merge commit*), Branch löschen.
6. Bei Änderungen am Code: CD-Lauf beobachten, bis die neue Version live ist.

```bash
git switch main && git pull
git switch -c feature/add-history-endpoint
# ... arbeiten ...
make check                         # Lint + Tests + Coverage lokal
git commit -m "feat(api): add /api/history endpoint"
git push -u origin feature/add-history-endpoint
# Pull Request auf GitHub öffnen
```

### Branch-Namen

Muster `<typ>/<kurzbeschreibung>`, Englisch, Kleinbuchstaben, Bindestriche.

| Typ | Zweck | Beispiel |
|---|---|---|
| `feature/` | neue Funktion | `feature/weather-cache` |
| `fix/` | Fehlerbehebung | `fix/ready-timeout` |
| `chore/` | Wartung, Werkzeuge | `chore/bump-gunicorn` |
| `ci/` | Pipeline | `ci/add-trivy-gate` |
| `docs/` | Dokumentation | `docs/deployment-runbook` |

## Commit-Konventionen

[Conventional Commits](https://www.conventionalcommits.org/), Englisch,
Imperativ, ohne Punkt am Ende:

```
<typ>(<optionaler bereich>): <kurze aussage>

<optionaler rumpf: warum, nicht was>
```

Typen: `feat`, `fix`, `docs`, `test`, `refactor`, `chore`, `ci`, `build`.

```
feat(api): serve stale snapshot when the weather API is down
fix(k8s): add writable /tmp for gunicorn heartbeat
ci: fail the build on CRITICAL vulnerabilities with a fix
```

## Selbstprüfung im Pull Request

Im Team ersetzt ein Review diesen Schritt; allein übernehme ich ihn selbst.
Jede PR-Beschreibung beantwortet:

- **Was** ändert dieser PR, und **warum**?
- Ist die CI grün (Lint, Test, Coverage-Gate, Build, Trivy, IaC-Checks)?
- Sind Tests für die Änderung vorhanden – oder warum nicht nötig?
- Ist die Doku angepasst (README, Runbook, ADR), falls nötig?
- Enthält der Diff keine Secrets?
- Bleibt etwas bewusst offen? Dann hier benennen.

Die Vorlage liegt in [.github/PULL_REQUEST_TEMPLATE.md](.github/PULL_REQUEST_TEMPLATE.md).

## Regeln

- Keine `--force`-Pushes auf `main`. Auf eigenen Feature-Branches ist ein
  Rebase vor dem Merge erlaubt.
- Nach dem Merge den Branch löschen.
- Secrets nie committen: `.env`, `terraform.tfstate`, `k8s/**/secret.yaml` sind
  ignoriert; die CI scannt jeden PR mit Trivy auf Secrets.
- Dependabot-PRs werden wie eigene PRs behandelt: CI grün, Changelog lesen,
  dann mergen.

## Vor jedem Push lokal prüfen

```bash
make check     # = ruff check . && ruff format --check . && pytest --cov=app
```

Mit lokalem Postgres laufen zusätzlich die Integrationstests:

```bash
docker run -d --name pg-test -e POSTGRES_PASSWORD=test -e POSTGRES_DB=test -p 55432:5432 postgres:16-alpine
TEST_DATABASE_URL=postgresql://postgres:test@localhost:55432/test make cov
docker rm -f pg-test
```
