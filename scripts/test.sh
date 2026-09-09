#!/usr/bin/env bash

set -e

echo "Backend tests"

uv run --directory backend python -m pytest

cd frontend

echo "Frontend production build"

npm run build
