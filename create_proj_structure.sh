#!/bin/bash

# create_meczyki_editorial.sh
# Creates the meczyki-editorial project structure

# Set base directory (default: ./meczyki-editorial)
BASE_DIR="${1:-.}"

echo "Creating project structure at: $BASE_DIR"

# Create all directories
mkdir -p "$BASE_DIR/backend/app"
mkdir -p "$BASE_DIR/frontend/app/login"
mkdir -p "$BASE_DIR/frontend/app/articles/[id]"
mkdir -p "$BASE_DIR/frontend/app/review/[id]"
mkdir -p "$BASE_DIR/frontend/app/search"
mkdir -p "$BASE_DIR/frontend/components"
mkdir -p "$BASE_DIR/frontend/lib"
mkdir -p "$BASE_DIR/database"

# Create backend files
touch "$BASE_DIR/backend/app/__init__.py"
touch "$BASE_DIR/backend/app/main.py"
touch "$BASE_DIR/backend/app/config.py"
touch "$BASE_DIR/backend/app/db.py"
touch "$BASE_DIR/backend/app/auth.py"
touch "$BASE_DIR/backend/app/schemas.py"
touch "$BASE_DIR/backend/app/articles.py"
touch "$BASE_DIR/backend/app/users.py"
touch "$BASE_DIR/backend/requirements.txt"
touch "$BASE_DIR/backend/.env.example"

# Create frontend files (app directory)
touch "$BASE_DIR/frontend/app/globals.css"
touch "$BASE_DIR/frontend/app/layout.tsx"
touch "$BASE_DIR/frontend/app/page.tsx"

# frontend/app/login/
touch "$BASE_DIR/frontend/app/login/page.tsx"

# frontend/app/articles/
touch "$BASE_DIR/frontend/app/articles/page.tsx"
touch "$BASE_DIR/frontend/app/articles/[id]/page.tsx"

# frontend/app/review/
touch "$BASE_DIR/frontend/app/review/[id]/page.tsx"

# frontend/app/search/
touch "$BASE_DIR/frontend/app/search/page.tsx"

# frontend/components/
touch "$BASE_DIR/frontend/components/ArticleEditor.tsx"
touch "$BASE_DIR/frontend/components/ArticleStatus.tsx"
touch "$BASE_DIR/frontend/components/Sidebar.tsx"
touch "$BASE_DIR/frontend/components/SourcePanel.tsx"

# frontend/lib/
touch "$BASE_DIR/frontend/lib/api.ts"
touch "$BASE_DIR/frontend/lib/auth.ts"
touch "$BASE_DIR/frontend/lib/types.ts"

# frontend root files
touch "$BASE_DIR/frontend/package.json"
touch "$BASE_DIR/frontend/tsconfig.json"
touch "$BASE_DIR/frontend/next.config.ts"
touch "$BASE_DIR/frontend/.env.local.example"
touch "$BASE_DIR/frontend/middleware.ts"

# database
touch "$BASE_DIR/database/init.sql"

echo "✅ Structure created successfully!"
echo "Tree:"
tree "$BASE_DIR" 2>/dev/null || find "$BASE_DIR" -type d -o -type f | sort