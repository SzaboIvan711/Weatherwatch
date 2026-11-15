.DEFAULT_GOAL := help
SHELL := /bin/bash

IMAGE      ?= weatherwatch
TAG        ?= local
VERSION    ?= 1.0.0
COMMIT     ?= $(shell git rev-parse HEAD 2>/dev/null || echo unknown)
CLUSTER    ?= weatherwatch
NAMESPACE  ?= weatherwatch
COMPOSE_MON = docker compose -f docker-compose.yml -f docker-compose.monitoring.yml

.PHONY: help install run test cov lint fmt check build whoami up down \
        monitoring-up monitoring-down load smoke trivy \
        tf-init tf-apply tf-destroy \
        kind-up k8s-load k8s-secret k8s-deploy k8s-status k8s-forward \
        k8s-update k8s-rollback kind-down

help: ## Zeigt diese Hilfe an
	@grep -E '^[a-z0-9-]+:.*?## ' $(MAKEFILE_LIST) | awk -F':.*?## ' '{printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

# --- Entwicklung -------------------------------------------------------------

install: ## Installiert alle Abhängigkeiten inkl. Dev-Tools (im aktiven venv)
	pip install -r requirements-dev.txt

run: ## Startet die App lokal auf Port 8000 (ohne DATABASE_URL: In-Memory)
	flask --app wsgi run --port 8000

test: ## Führt die Testsuite aus
	pytest

cov: ## Testsuite mit Coverage-Bericht und Gate (80 %)
	pytest --cov=app --cov-report=term-missing

lint: ## Prüft Stil, Importe und Sicherheitsregeln (ruff)
	ruff check .
	ruff format --check .

fmt: ## Formatiert den Code
	ruff check --fix .
	ruff format .

check: lint cov ## Alles, was die CI prüft (vor jedem Push)

# --- Container ---------------------------------------------------------------

build: ## Baut das Container-Image $(IMAGE):$(TAG)
	docker build --build-arg APP_VERSION=$(VERSION) --build-arg GIT_COMMIT=$(COMMIT) -t $(IMAGE):$(TAG) .

whoami: build ## Zeigt, unter welchem Benutzer der Container läuft (nicht root)
	docker run --rm $(IMAGE):$(TAG) whoami

up: ## Startet App + Datenbank via Docker Compose
	docker compose up --build

down: ## Stoppt Docker Compose (Volume bleibt erhalten)
	docker compose down

monitoring-up: ## Startet App, DB, Prometheus und Grafana
	$(COMPOSE_MON) up -d --build

monitoring-down: ## Stoppt den Monitoring-Stack
	$(COMPOSE_MON) down

load: ## Erzeugt Last gegen http://localhost:8000 (URL=... überschreibt)
	bash scripts/last-erzeugen.sh $(or $(URL),http://localhost:8000)

smoke: ## Smoke-Test gegen eine laufende Instanz (URL=... überschreibt)
	bash scripts/smoke-test.sh $(or $(URL),http://localhost:8000)

trivy: build ## Scannt das Image lokal mit Trivy (gleicher Schwellwert wie CI)
	trivy image --severity CRITICAL --ignore-unfixed --exit-code 1 $(IMAGE):$(TAG)

# --- Terraform ---------------------------------------------------------------

tf-init: ## terraform init + validate
	terraform -chdir=terraform init
	terraform -chdir=terraform validate

tf-apply: build ## Baut das Image und startet App + DB per Terraform
	terraform -chdir=terraform apply -var="image=$(IMAGE):$(TAG)"

tf-destroy: ## Entfernt alle Terraform-Ressourcen
	terraform -chdir=terraform destroy -var="image=$(IMAGE):$(TAG)"

# --- Kubernetes (kind) -------------------------------------------------------

kind-up: ## Erzeugt den kind-Cluster (1 Control-Plane, 2 Worker)
	kind create cluster --config k8s/kind/kind-config.yaml
	kubectl cluster-info --context kind-$(CLUSTER)

k8s-load: build ## Baut das Image und lädt es in den kind-Cluster
	kind load docker-image $(IMAGE):$(TAG) --name $(CLUSTER)

k8s-secret: ## Legt das DB-Secret mit Zufallspasswort an (idempotent)
	kubectl apply -f k8s/00-namespace.yaml
	@kubectl -n $(NAMESPACE) get secret weatherwatch-db >/dev/null 2>&1 \
	  && echo "secret weatherwatch-db exists, keeping it" \
	  || kubectl -n $(NAMESPACE) create secret generic weatherwatch-db \
	       --from-literal=POSTGRES_PASSWORD="$$(openssl rand -hex 24)"

k8s-deploy: k8s-secret ## Wendet alle Manifeste an und wartet auf den Rollout
	kubectl apply -f k8s/
	kubectl -n $(NAMESPACE) rollout status statefulset/weatherwatch-db --timeout=180s
	kubectl -n $(NAMESPACE) rollout status deployment/weatherwatch --timeout=180s

k8s-status: ## Zeigt Pods (mit Knoten), Deployment, Services
	kubectl -n $(NAMESPACE) get pods -o wide
	kubectl -n $(NAMESPACE) get deployment,statefulset,service,pdb

k8s-forward: ## Service lokal unter http://localhost:8080 verfügbar machen
	kubectl -n $(NAMESPACE) port-forward service/weatherwatch 8080:80

k8s-update: ## Rolling Update auf $(IMAGE):v2 (Version 1.1.0)
	docker build --build-arg APP_VERSION=1.1.0 --build-arg GIT_COMMIT=$(COMMIT) -t $(IMAGE):v2 .
	kind load docker-image $(IMAGE):v2 --name $(CLUSTER)
	kubectl -n $(NAMESPACE) set image deployment/weatherwatch weatherwatch=$(IMAGE):v2
	kubectl -n $(NAMESPACE) rollout status deployment/weatherwatch

k8s-rollback: ## Letztes Rollout rückgängig machen
	kubectl -n $(NAMESPACE) rollout undo deployment/weatherwatch
	kubectl -n $(NAMESPACE) rollout status deployment/weatherwatch

kind-down: ## Löscht den kind-Cluster
	kind delete cluster --name $(CLUSTER)
