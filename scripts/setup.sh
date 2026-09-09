#!/usr/bin/env bash

set -e

echo "== Meczyki Editorial setup =="

echo "Checking Python..."
uv run python --version

echo "Checking Node..."
node --version

echo "Installing backend (uv)..."
uv sync

echo "Installing frontend..."
cd frontend
npm install
cd ..

echo
echo "Setup complete."
echo
echo "Next:"
echo "  1. configure .env"
echo "  2. configure frontend/.env.local"
echo "  3. run make db-init"
echo "  4. run make dev"
