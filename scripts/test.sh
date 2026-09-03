#!/usr/bin/env bash

set -e

echo "Backend tests"

cd backend

source .venv/bin/activate

python -m pytest

cd ../frontend

echo "Frontend production build"

npm run build