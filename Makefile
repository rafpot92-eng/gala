.PHONY: setup backend frontend dev test db-init ingest \
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
	uv run --directory backend python scripts/ingest.py

databricks-validate:
	./scripts/databricks-deploy.sh validate

databricks-deploy:
	./scripts/databricks-deploy.sh deploy