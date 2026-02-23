#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}/design-library-indexer"
"${SCRIPT_DIR}/venv/bin/python" run_indexer.py search "$@"
