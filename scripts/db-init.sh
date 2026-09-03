#!/usr/bin/env bash

set -e

if [ -z "$DATABASE_URL" ]; then
    echo "DATABASE_URL is not set."
    exit 1
fi

echo "Initializing database..."

psql "$DATABASE_URL" \
    -f database/001_schema.sql

psql "$DATABASE_URL" \
    -f database/002_indexes.sql

if [ "${ENVIRONMENT:-development}" = "development" ]; then

    psql "$DATABASE_URL" \
        -f database/003_seed_development.sql

fi

echo "Database initialized."