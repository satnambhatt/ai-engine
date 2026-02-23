#!/bin/bash
# Search and display full file content for the top result
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}/design-library-indexer"

RESULT=$("${SCRIPT_DIR}/venv/bin/python" -c "
import sys, logging
logging.disable(logging.CRITICAL)
from indexer.config import IndexerConfig
from indexer.embeddings import EmbeddingClient
from indexer.store import VectorStore

config = IndexerConfig()
embedder = EmbeddingClient(config)
store = VectorStore(config)
store.initialize()

result = embedder.embed('$1')
if result:
    results = store.search(query_embedding=result.embedding, n_results=1)
    if results:
        print(results[0].file_path)
" 2>/dev/null)

if [ -n "$RESULT" ]; then
    FULL_PATH="/mnt/design-library/$RESULT"
    echo "=== $RESULT ==="
    echo ""
    cat "$FULL_PATH"
else
    echo "No results found"
fi
