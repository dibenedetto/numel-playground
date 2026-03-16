#!/usr/bin/env bash
# =============================================================================
# Numel Playground — Linux / macOS launcher
# Installs uv (if missing), downloads Python 3.12, syncs dependencies,
# then starts the application.
# Usage:  ./run.sh [app arguments...]
# =============================================================================
set -euo pipefail

UV_PYTHON="3.12"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ── 1. Ensure uv is available ─────────────────────────────────────────────────
if ! command -v uv &>/dev/null; then
    echo "[numel] uv not found — installing..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    # The installer adds ~/.local/bin; source env so PATH is updated
    export PATH="$HOME/.local/bin:$PATH"
    if ! command -v uv &>/dev/null; then
        echo "[numel] ERROR: uv installation failed. Please install manually:"
        echo "        https://docs.astral.sh/uv/getting-started/installation/"
        exit 1
    fi
    echo "[numel] uv installed: $(uv --version)"
else
    echo "[numel] uv found: $(uv --version)"
fi

# ── 2. Ensure Python 3.12 is available ───────────────────────────────────────
cd "$SCRIPT_DIR"
echo "[numel] Checking Python ${UV_PYTHON}..."
uv python install "$UV_PYTHON" --quiet

# ── 3. Sync dependencies (create / update .venv) ─────────────────────────────
echo "[numel] Syncing dependencies..."
uv sync --quiet

# ── 4. Run the application ────────────────────────────────────────────────────
echo "[numel] Starting Numel Playground..."
exec uv run python app/app.py "$@"
