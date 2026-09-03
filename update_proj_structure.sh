#!/bin/bash
# create_meczyki_editorial.sh
# Idempotent structure creator for meczyki-editorial project

set -e  # exit on error

BASE_DIR="${1:-./}"
mkdir -p "$BASE_DIR"  # ensure base exists

# ---------- Helper: create directory if not exists ----------
mkd() {
    [ -d "$1" ] || mkdir -p "$1"
}

# ---------- Helper: create file only if missing ----------
mkf() {
    [ -f "$1" ] || touch "$1"
}

echo "Creating structure in: $BASE_DIR"

# 1. Directories
mkd "$BASE_DIR/backend/app"
mkd "$BASE_DIR/frontend/app/login"
mkd "$BASE_DIR/frontend/app/articles"
mkd "$BASE_DIR/frontend/app/review/[id]"
mkd "$BASE_DIR/frontend/app/search"
mkd "$BASE_DIR/frontend/components"
mkd "$BASE_DIR/frontend/lib"
mkd "$BASE_DIR/database"
mkd "$BASE_DIR/databricks/notebooks"
mkd "$BASE_DIR/databricks/src/meczyki"
mkd "$BASE_DIR/databricks/src/editorial"
mkd "$BASE_DIR/databricks/sql"
mkd "$BASE_DIR/databricks/jobs"
mkd "$BASE_DIR/config"
mkd "$BASE_DIR/scripts"
mkd "$BASE_DIR/docs"

# 2. Files (root)
mkf "$BASE_DIR/README.md"
mkf "$BASE_DIR/Makefile"
mkf "$BASE_DIR/.gitignore"
mkf "$BASE_DIR/.env.example"

# 3. Backend
mkf "$BASE_DIR/backend/app/__init__.py"
mkf "$BASE_DIR/backend/app/main.py"
mkf "$BASE_DIR/backend/app/config.py"
mkf "$BASE_DIR/backend/app/db.py"
mkf "$BASE_DIR/backend/app/auth.py"
mkf "$BASE_DIR/backend/app/schemas.py"
mkf "$BASE_DIR/backend/app/articles.py"
mkf "$BASE_DIR/backend/app/users.py"
mkf "$BASE_DIR/backend/app/search.py"
mkf "$BASE_DIR/backend/requirements.txt"
mkf "$BASE_DIR/backend/.env.example"

# 4. Frontend
mkf "$BASE_DIR/frontend/app/globals.css"
mkf "$BASE_DIR/frontend/app/layout.tsx"
mkf "$BASE_DIR/frontend/app/page.tsx"
mkf "$BASE_DIR/frontend/app/login/page.tsx"
mkf "$BASE_DIR/frontend/app/articles/page.tsx"
mkf "$BASE_DIR/frontend/app/review/[id]/page.tsx"
mkf "$BASE_DIR/frontend/app/search/page.tsx"
# components/ and lib/ are already directories (no files initially)
mkf "$BASE_DIR/frontend/package.json"
mkf "$BASE_DIR/frontend/next.config.ts"
mkf "$BASE_DIR/frontend/.env.local.example"

# 5. Database
mkf "$BASE_DIR/database/001_schema.sql"
mkf "$BASE_DIR/database/002_indexes.sql"
mkf "$BASE_DIR/database/003_seed_development.sql"
mkf "$BASE_DIR/database/README.md"

# 6. Databricks
mkf "$BASE_DIR/databricks/README.md"
mkf "$BASE_DIR/databricks/notebooks/01_ingest.py"
mkf "$BASE_DIR/databricks/notebooks/02_embed.py"
mkf "$BASE_DIR/databricks/notebooks/03_editorial_agent.py"
mkf "$BASE_DIR/databricks/notebooks/04_search.py"
mkf "$BASE_DIR/databricks/src/meczyki/__init__.py"
mkf "$BASE_DIR/databricks/src/meczyki/discovery.py"
mkf "$BASE_DIR/databricks/src/meczyki/parser.py"
mkf "$BASE_DIR/databricks/src/meczyki/models.py"
mkf "$BASE_DIR/databricks/src/meczyki/utils.py"
mkf "$BASE_DIR/databricks/src/editorial/__init__.py"
mkf "$BASE_DIR/databricks/src/editorial/agent.py"
mkf "$BASE_DIR/databricks/src/editorial/prompts.py"
mkf "$BASE_DIR/databricks/src/editorial/retrieval.py"
mkf "$BASE_DIR/databricks/sql/001_bronze.sql"
mkf "$BASE_DIR/databricks/sql/002_silver.sql"
mkf "$BASE_DIR/databricks/sql/003_gold.sql"
mkf "$BASE_DIR/databricks/jobs/hourly_ingestion.yml"
mkf "$BASE_DIR/databricks/jobs/embedding.yml"
mkf "$BASE_DIR/databricks/jobs/editorial_agent.yml"

# 7. Config
mkf "$BASE_DIR/config/development.yml"
mkf "$BASE_DIR/config/staging.yml"
mkf "$BASE_DIR/config/production.yml"

# 8. Scripts
mkf "$BASE_DIR/scripts/setup.sh"
mkf "$BASE_DIR/scripts/dev.sh"
mkf "$BASE_DIR/scripts/test.sh"
mkf "$BASE_DIR/scripts/db-init.sh"
mkf "$BASE_DIR/scripts/databricks-deploy.sh"

# 9. Docs
mkf "$BASE_DIR/docs/architecture.md"
mkf "$BASE_DIR/docs/development.md"
mkf "$BASE_DIR/docs/databricks.md"
mkf "$BASE_DIR/docs/database.md"
mkf "$BASE_DIR/docs/ingestion.md"
mkf "$BASE_DIR/docs/embeddings.md"
mkf "$BASE_DIR/docs/editorial-agent.md"
mkf "$BASE_DIR/docs/authentication.md"
mkf "$BASE_DIR/docs/api.md"
mkf "$BASE_DIR/docs/deployment.md"
mkf "$BASE_DIR/docs/operations.md"
mkf "$BASE_DIR/docs/troubleshooting.md"

echo "✅ Structure ready at $BASE_DIR"
echo ""
if command -v tree >/dev/null 2>&1; then
    tree "$BASE_DIR"
else
    echo "Tip: install 'tree' for a nicer view."
    find "$BASE_DIR" -type d -o -type f | sort
fi