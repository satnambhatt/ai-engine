#!/usr/bin/env bash
set -euo pipefail

# ══════════════════════════════════════════════════════════════
# start.sh — Kick-start the full AI RAG stack
# ══════════════════════════════════════════════════════════════
#
# Brings up every component needed for the design-library RAG
# pipeline in the right order:
#
#   1. Python virtual environment + dependency install
#   2. Ollama (embedding server)
#   3. Embedding model pull (if missing)
#   4. ChromaDB data directory
#   5. Initial full index (background)
#   6. File watcher (background)
#
# Usage:
#     chmod +x start.sh
#     ./start.sh                 # full index + watcher
#     ./start.sh --incremental   # incremental index + watcher
#     ./start.sh --index-only    # index only, no watcher
#     ./start.sh --watcher-only  # watcher only, no index
#
# Logs:
#     tail -f <ENGINE_DIR>/logs/start-index.log
#     tail -f <ENGINE_DIR>/logs/start-watcher.log
#
# ══════════════════════════════════════════════════════════════

# ── Resolve paths ─────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENGINE_DIR="${SCRIPT_DIR}"
INDEXER_DIR="${ENGINE_DIR}/design-library-indexer"
VENV_DIR="${ENGINE_DIR}/venv"
LOG_DIR="${ENGINE_DIR}/logs"
REQUIREMENTS="${INDEXER_DIR}/requirements.txt"

# Load storage config from .env (written by setup.sh)
ENV_FILE="${ENGINE_DIR}/.env"
if [ -f "${ENV_FILE}" ]; then
    # shellcheck source=/dev/null
    set -o allexport; source "${ENV_FILE}"; set +o allexport
fi

# Fallback defaults if .env is missing
LIBRARY_ROOT="${LIBRARY_ROOT:-/mnt/design-library}"
CHROMA_DIR="${CHROMA_DIR:-/mnt/design-library/chroma_data}"
OLLAMA_URL="http://localhost:11434"
EMBEDDING_MODEL="nomic-embed-text"

# ── Parse arguments ───────────────────────────────────────────
INDEX_MODE="full"      # full | incremental | none
RUN_WATCHER=true

for arg in "$@"; do
    case "$arg" in
        --incremental)  INDEX_MODE="incremental" ;;
        --index-only)   RUN_WATCHER=false ;;
        --watcher-only) INDEX_MODE="none" ;;
        --help|-h)
            echo "Usage: ./start.sh [--incremental] [--index-only] [--watcher-only]"
            echo ""
            echo "  (default)       Full index in background + file watcher"
            echo "  --incremental   Incremental index (only changed files) + watcher"
            echo "  --index-only    Run index only, do not start the file watcher"
            echo "  --watcher-only  Start the file watcher only, skip indexing"
            exit 0
            ;;
        *)
            echo "Unknown argument: $arg"
            echo "Run ./start.sh --help for usage."
            exit 1
            ;;
    esac
done

# ── Helpers ───────────────────────────────────────────────────
info()  { echo -e "\033[1;34m[INFO]\033[0m  $*"; }
ok()    { echo -e "\033[1;32m[OK]\033[0m    $*"; }
warn()  { echo -e "\033[1;33m[WARN]\033[0m  $*"; }
fail()  { echo -e "\033[1;31m[FAIL]\033[0m  $*"; exit 1; }

# ══════════════════════════════════════════════════════════════
# 1. Python virtual environment + dependencies
# ══════════════════════════════════════════════════════════════
info "Checking Python virtual environment..."

if [ ! -d "${VENV_DIR}" ]; then
    info "Creating virtual environment at ${VENV_DIR}..."
    python3 -m venv "${VENV_DIR}"
    ok "Virtual environment created"
else
    ok "Virtual environment exists at ${VENV_DIR}"
fi

PYTHON="${VENV_DIR}/bin/python"
PIP="${VENV_DIR}/bin/pip"

if [ ! -f "${REQUIREMENTS}" ]; then
    fail "requirements.txt not found at ${REQUIREMENTS}"
fi

info "Installing Python dependencies..."
"${PIP}" install -q --upgrade pip
"${PIP}" install -q -r "${REQUIREMENTS}"
ok "Python dependencies installed"

# ══════════════════════════════════════════════════════════════
# 2. Ollama — ensure the embedding server is running
# ══════════════════════════════════════════════════════════════
info "Checking Ollama..."

OLLAMA_RUNNING=false
for i in 1 2 3; do
    if curl -sf "${OLLAMA_URL}/api/tags" > /dev/null 2>&1; then
        OLLAMA_RUNNING=true
        break
    fi
    if [ "$i" -eq 1 ]; then
        info "Ollama not responding, attempting to start..."
        ollama serve > /dev/null 2>&1 &
        disown
    fi
    sleep 2
done

if [ "${OLLAMA_RUNNING}" = false ]; then
    fail "Could not connect to Ollama at ${OLLAMA_URL}. Is it installed? Run: curl -fsSL https://ollama.com/install.sh | sh"
fi
ok "Ollama is running"

# ══════════════════════════════════════════════════════════════
# 3. Embedding model — pull if not present
# ══════════════════════════════════════════════════════════════
info "Checking embedding model '${EMBEDDING_MODEL}'..."

MODEL_AVAILABLE=$(curl -sf "${OLLAMA_URL}/api/tags" | "${PYTHON}" -c "
import sys, json
data = json.load(sys.stdin)
models = [m.get('name','') for m in data.get('models',[])]
print('yes' if any('${EMBEDDING_MODEL}' in m for m in models) else 'no')
" 2>/dev/null || echo "no")

if [ "${MODEL_AVAILABLE}" = "no" ]; then
    info "Pulling ${EMBEDDING_MODEL} (this may take a few minutes)..."
    ollama pull "${EMBEDDING_MODEL}"
    ok "Model '${EMBEDDING_MODEL}' pulled"
else
    ok "Model '${EMBEDDING_MODEL}' is available"
fi

# ══════════════════════════════════════════════════════════════
# 4. Directory structure
# ══════════════════════════════════════════════════════════════
info "Verifying directories..."

mkdir -p "${LOG_DIR}"

if [ ! -d "${LIBRARY_ROOT}" ]; then
    warn "Library root ${LIBRARY_ROOT} does not exist. Indexing will fail until it is mounted."
fi

ok "Log directory ready at ${LOG_DIR}"

# ══════════════════════════════════════════════════════════════
# 5. Stop any existing indexer/watcher processes
# ══════════════════════════════════════════════════════════════
info "Stopping any existing indexer or watcher processes..."

pkill -f "run_indexer.py index" 2>/dev/null && info "Stopped existing indexer" || true
pkill -f "watch_library.py"    2>/dev/null && info "Stopped existing watcher" || true

# Brief pause to let processes clean up
sleep 1

# ══════════════════════════════════════════════════════════════
# 6. Start indexing (background)
# ══════════════════════════════════════════════════════════════
INDEX_LOG="${LOG_DIR}/start-index.log"
INDEX_PID=""

if [ "${INDEX_MODE}" != "none" ]; then
    if [ "${INDEX_MODE}" = "full" ]; then
        INDEX_FLAG="--full"
        info "Starting FULL index in background..."
    else
        INDEX_FLAG=""
        info "Starting INCREMENTAL index in background..."
    fi

    (
        cd "${INDEXER_DIR}"
        "${PYTHON}" run_indexer.py index ${INDEX_FLAG} -v
    ) > "${INDEX_LOG}" 2>&1 &
    INDEX_PID=$!
    disown

    ok "Indexer running (PID ${INDEX_PID}) — log: ${INDEX_LOG}"
fi

# ══════════════════════════════════════════════════════════════
# 7. Start file watcher (background)
# ══════════════════════════════════════════════════════════════
WATCHER_LOG="${LOG_DIR}/start-watcher.log"
WATCHER_PID=""

if [ "${RUN_WATCHER}" = true ]; then
    info "Starting file watcher in background..."

    (
        cd "${INDEXER_DIR}"
        "${PYTHON}" watch_library.py --library-root "${LIBRARY_ROOT}" --debounce 30
    ) > "${WATCHER_LOG}" 2>&1 &
    WATCHER_PID=$!
    disown

    ok "Watcher running (PID ${WATCHER_PID}) — log: ${WATCHER_LOG}"
fi

# ══════════════════════════════════════════════════════════════
# 8. Summary
# ══════════════════════════════════════════════════════════════
echo ""
echo "======================================================="
echo "  AI RAG Stack — Running"
echo "======================================================="
echo ""
echo "  Ollama:       ${OLLAMA_URL} (${EMBEDDING_MODEL})"
echo "  Library root: ${LIBRARY_ROOT}"
echo "  ChromaDB:     ${CHROMA_DIR}"
echo "  Venv:         ${VENV_DIR}"
echo ""
if [ -n "${INDEX_PID}" ]; then
echo "  Indexer:       PID ${INDEX_PID} (${INDEX_MODE} mode)"
echo "                 tail -f ${INDEX_LOG}"
fi
if [ -n "${WATCHER_PID}" ]; then
echo "  Watcher:       PID ${WATCHER_PID}"
echo "                 tail -f ${WATCHER_LOG}"
fi
echo ""
echo "  Quick search:  cd ${INDEXER_DIR} && ${PYTHON} run_indexer.py search \"hero section\""
echo "  Index stats:   cd ${INDEXER_DIR} && ${PYTHON} run_indexer.py stats"
echo "  Stop all:      pkill -f run_indexer.py; pkill -f watch_library.py"
echo ""
echo "======================================================="
