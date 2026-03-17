#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# AI Migration Platform — single-command startup script
#
# Usage:
#   ./scripts/start.sh              # development (auto-reload)
#   ./scripts/start.sh --prod       # production (no reload, 4 workers)
#   ./scripts/start.sh --install    # pip install + start
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$ROOT_DIR"

# ── Resolve uvicorn / python from .venv if present ───────────────────────────
if [ -f ".venv/bin/uvicorn" ]; then
    UVICORN=".venv/bin/uvicorn"
else
    UVICORN="uvicorn"
fi

# ── Parse flags ──────────────────────────────────────────────────────────────
PROD=false
INSTALL=false
for arg in "$@"; do
    case $arg in
        --prod)    PROD=true ;;
        --install) INSTALL=true ;;
    esac
done

# ── Install dependencies ──────────────────────────────────────────────────────
if [ "$INSTALL" = true ]; then
    echo "▶  Installing dependencies from pyproject.toml..."
    if [ -f ".venv/bin/pip" ]; then
        .venv/bin/pip install -e ".[dev]" --quiet
    else
        pip install -e ".[dev]" --quiet
    fi
    echo "✓  Dependencies installed"
fi

# ── Validate .env exists ──────────────────────────────────────────────────────
if [ ! -f .env ]; then
    echo "⚠  .env not found — copying from .env.example"
    cp .env.example .env
    echo "   Edit .env and add your ANTHROPIC_API_KEY and OPENAI_API_KEY"
    echo "   Then re-run: ./scripts/start.sh"
    exit 1
fi

# ── Create data directories (no server needed — pure Python stores) ───────────
mkdir -p data/chroma data/cache repos output

echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║     AI Migration Platform — In-Memory Edition                ║"
echo "║                                                              ║"
echo "║  Graph store : NetworkX  (./data/graph.pkl)                  ║"
echo "║  Vector store: ChromaDB  (./data/chroma/)                    ║"
echo "║  State store : DuckDB    (./data/migration.duckdb)           ║"
echo "║  Cache store : diskcache (./data/cache/)                     ║"
echo "║                                                              ║"
echo "║  No Docker. No database servers. Just: python.               ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

# ── Start the platform ────────────────────────────────────────────────────────
if [ "$PROD" = true ]; then
    echo "▶  Starting in PRODUCTION mode (4 workers, no reload)..."
    PYTHONPATH=src $UVICORN migration_platform.main:app \
        --host 0.0.0.0 \
        --port "${PORT:-8000}" \
        --workers 4 \
        --log-level info
else
    echo "▶  Starting in DEVELOPMENT mode (auto-reload enabled)..."
    echo "   API:       http://localhost:${PORT:-8000}"
    echo "   Docs:      http://localhost:${PORT:-8000}/docs"
    echo "   Health:    http://localhost:${PORT:-8000}/health"
    echo ""
    PYTHONPATH=src $UVICORN migration_platform.main:app \
        --host 0.0.0.0 \
        --port "${PORT:-8000}" \
        --reload \
        --reload-dir src \
        --log-level debug
fi
