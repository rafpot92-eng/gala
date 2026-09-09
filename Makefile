.PHONY: setup backend frontend dev test db-init \
        databricks-validate databricks-deploy

setup:
	./scripts/setup.sh

backend:
	uv run --directory backend uvicorn app.main:app --reload --port 8000

frontend:
	cd frontend && npm run dev

dev:
	./scripts/dev.sh

test:
	./scripts/test.sh

db-init:
	./scripts/db-init.sh

ingest:
	@echo "Ingestion runs in Databricks notebook 01_ingest.py (see databricks/jobs/hourly_ingestion.yml)"
	@echo "Local ad-hoc run not supported; use the Databricks hourly job."

databricks-validate:
	./scripts/databricks-deploy.sh validate

databricks-deploy:
	./scripts/databricks-deploy.sh deploy