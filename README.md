# AI Engine

AI-powered design system with semantic search, RAG code generation, and IDE integration — running entirely on a Raspberry Pi 4.

## What It Does

Indexes your design library (HTML, CSS, JS, React, Vue, etc.) into a vector database, then uses retrieval-augmented generation (RAG) to search, generate code, and audit SEO — all from a web UI, CLI, or directly in your IDE via MCP.

```bash
# Find code by description
./search.sh "hero section with gradient background"
./search.sh "responsive navigation with dropdown"
./search.sh "animated loading spinner"
./search.sh "pricing table with three columns"
```

## Full System Architecture

```
Browser (LAN :80)                     IDE (Claude Code / VS Code)
       |                                        |
       v                                        v (stdio)
nginx reverse proxy (:80)              MCP Server (mcp-server/server.py)
       |                                        |
       |-- /* --> static frontend               | httpx
       |-- /api/* --> proxy to :8000            |
       v                                        v
              FastAPI RAG API (:8000)
              |           |           |
              v           v           v
          Ollama      ChromaDB    BeautifulSoup
        (LLM+Embed)  (vectors)    (SEO audit)
              |
              v
    USB SSD: /mnt/design-library/
```

### Components

| Component | Port | Purpose |
|-----------|------|---------|
| **nginx** | 80 | Serves frontend, proxies `/api/*` to RAG API |
| **RAG API** (FastAPI) | 8000 | Search, generate, templates, SEO audit endpoints |
| **MCP Server** | stdio | Exposes RAG tools to Claude Code / VS Code |
| **Ollama** | 11434 | Local LLM (qwen2.5-coder:3b) and embeddings (nomic-embed-text) |
| **ChromaDB** | embedded | Vector database for semantic search |
| **Indexer** | n/a | Processes design files into embeddings |
| **File Watcher** | n/a | Auto-indexes new files (systemd service) |

### Data Flow

1. **Indexing:** Design files on USB SSD are chunked, embedded via Ollama (nomic-embed-text, 768-dim), and stored in ChromaDB
2. **Search:** User query is embedded, ChromaDB finds nearest vectors by cosine similarity, returns matching code
3. **Generation:** User brief is embedded, top N matching chunks are retrieved as context, injected into a task-specific prompt with design rules, sent to Ollama (qwen2.5-coder:3b) for code generation
4. **SEO Audit:** HTML is parsed with BeautifulSoup and checked against 11 SEO rules (no LLM needed)

### Access Methods

| Method | How | Best For |
|--------|-----|----------|
| **Web UI** | `http://<pi-ip>/` from any device on LAN | Visual browsing, quick searches, code generation |
| **CLI** | `./search.sh "query"` on the Pi | Quick terminal searches |
| **API** | `curl http://localhost:8000/search` | Scripts, automation, integrations |
| **MCP (IDE)** | Claude Code / VS Code tools | Generating code within your editor workflow |

## Web UI

Access the frontend from any device on the local network at `http://<pi-ip>/`.

Four tabs:
- **Search** — Semantic search with framework/category filters and code preview
- **Generate** — RAG-powered code generation with live progress timer
- **Templates** — Browse templates across 16 categories
- **SEO Audit** — Paste HTML, get a score out of 100 with detailed findings

### Setup

```bash
# Install nginx
sudo apt-get install -y nginx

# Configure
sudo cp /home/rpi/ai-engine/setup-ai-process/nginx-ai-engine.conf /etc/nginx/sites-available/ai-engine
sudo ln -sf /etc/nginx/sites-available/ai-engine /etc/nginx/sites-enabled/ai-engine
sudo rm -f /etc/nginx/sites-enabled/default
sudo chmod o+x /home/rpi
sudo nginx -t && sudo systemctl reload nginx
```

See [docs/frontend.md](docs/frontend.md) for details.

## RAG API

FastAPI server on port 8000 providing:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | System status (Ollama, ChromaDB, chunk count) |
| `/search` | POST | Semantic search across the design library |
| `/generate` | POST | RAG-powered code generation from a brief |
| `/templates/{category}` | GET | List templates by category |
| `/seo/audit` | POST | SEO audit on HTML content |

### Start the API

```bash
cd /home/rpi/ai-engine/rag-api
nohup /home/rpi/ai-engine/venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000 \
  > /home/rpi/ai-engine/logs/rag-api.log 2>&1 &
```

See [docs/rag-api.md](docs/rag-api.md) for endpoint examples and request/response schemas.

## MCP Server (IDE Integration)

Exposes 5 RAG tools to Claude Code and VS Code via the Model Context Protocol:

| Tool | Description |
|------|-------------|
| `search_design_library` | Semantic search with framework/category filters |
| `generate_code` | RAG-powered code generation from a brief |
| `list_templates` | Browse templates by category |
| `seo_audit` | Audit HTML for SEO issues |
| `health_check` | System status check |

### Setup for Claude Code

```bash
claude mcp add design-rag -- /home/rpi/ai-engine/venv/bin/python /home/rpi/ai-engine/mcp-server/server.py
```

### Setup for VS Code

Create `.vscode/mcp.json` in your workspace:

```json
{
  "servers": {
    "design-rag": {
      "type": "stdio",
      "command": "/home/rpi/ai-engine/venv/bin/python",
      "args": ["/home/rpi/ai-engine/mcp-server/server.py"]
    }
  }
}
```

See [docs/mcp-server.md](docs/mcp-server.md) for full tool reference and troubleshooting.

## Quick Start

### 1. Setup (first time only)

```bash
cd /home/rpi/ai-engine
chmod +x setup.sh
sudo ./setup.sh

# To also enable systemd services on boot:
sudo ENABLE_SERVICES=true ./setup.sh
```

### 2. Index your library

```bash
cd /home/rpi/ai-engine/design-library-indexer

# Full index (first time)
/home/rpi/ai-engine/venv/bin/python run_indexer.py index --full -v

# Incremental index (after first time - only new/changed files)
/home/rpi/ai-engine/venv/bin/python run_indexer.py index -v
```

### 3. Background indexing

```bash
# Run in background with logging
cd /home/rpi/ai-engine/design-library-indexer
nohup /home/rpi/ai-engine/venv/bin/python run_indexer.py index --full -v \
  > /home/rpi/ai-engine/logs/full-index-$(date +%Y%m%d-%H%M%S).log 2>&1 &

# Monitor progress
tail -f /home/rpi/ai-engine/logs/indexer-manual.log
```

### 4. Stop and resume

```bash
# Stop indexing anytime
pkill -f "run_indexer.py"

# Resume later (automatically picks up where it left off)
cd /home/rpi/ai-engine/design-library-indexer
nohup /home/rpi/ai-engine/venv/bin/python run_indexer.py index -v \
  > /home/rpi/ai-engine/logs/index-resume-$(date +%Y%m%d-%H%M%S).log 2>&1 &

# 1. Kill the old RAG API
pkill -f "uvicorn main:app"

# 2. Start the new RAG API with increased timeout
cd /home/rpi/ai-engine/rag-api
nohup /home/rpi/ai-engine/venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000 \
  > /home/rpi/ai-engine/logs/rag-api.log 2>&1 &

# 3. Copy the updated nginx config and reload
sudo cp /home/rpi/ai-engine/setup-ai-process/nginx-ai-engine.conf /etc/nginx/sites-available/ai-engine
sudo ln -sf /etc/nginx/sites-available/ai-engine /etc/nginx/sites-enabled/ai-engine
sudo rm -f /etc/nginx/sites-enabled/default
sudo chmod o+x /home/rpi /home/rpi/ai-engine /home/rpi/ai-engine/frontend
sudo chmod o+r /home/rpi/ai-engine/frontend/index.html
sudo nginx -t && sudo systemctl start nginx && sudo systemctl reload nginx
```

Resume works because the system saves SHA256 hashes after each file. On re-run, it skips already-indexed files.

## Searching

### Basic search

```bash
./search.sh "animated loading spinner"
```

### Search with full code output

```bash
# Show complete chunk code instead of 3-line preview
./search.sh "animated loader" --show-code
```

### Search with filters

```bash
# Filter by framework
./search.sh "card component with hover effect" --framework html
./search.sh "useState hook example" --framework react
./search.sh "loading animation keyframes" --framework css

# Get more results
./search.sh "hero section" -n 15

# Include <head> meta chunks (excluded by default to avoid boilerplate)
./search.sh "meta tags open graph" --include-head
```

### Understanding results

```
[1] example-websites/tailwind/hyperui/public/components/application/loaders/1.html
    Similarity: 0.72 | Framework: html | Category: n/a | Section: section
    Repo: hyperui
    Preview: <div class="flex items-center justify-center">
             <div class="h-16 w-16 animate-spin rounded-full border-4...
```

| Score | Meaning |
|-------|---------|
| 0.80+ | Exact match |
| 0.60-0.80 | Good match - relevant code |
| 0.45-0.60 | Weak match - loosely related |
| < 0.45 | Probably not relevant |

### Using results as code samples

Search results include file paths. Use them to grab full source code:

```bash
# View full file from a search result
cat /mnt/design-library/example-websites/tailwind/hyperui/public/components/application/loaders/1.html

# Copy to your project
cp /mnt/design-library/path/to/result.html ~/my-project/components/
```

### Combine searches for complete components

```bash
# Find HTML structure
./search.sh "pricing table markup" --framework html

# Find the CSS styling
./search.sh "pricing table styles" --framework css

# Find JavaScript behavior
./search.sh "pricing toggle monthly yearly" --framework javascript
```

## Services

### File watcher (auto-indexes new files)

```bash
sudo systemctl start design-library-watcher
sudo systemctl stop design-library-watcher
sudo systemctl status design-library-watcher
```

### Nightly re-index (2 AM daily)

```bash
sudo systemctl start design-library-reindex.timer
sudo systemctl stop design-library-reindex.timer
```

### Log rotation

Log rotation is configured automatically during setup via `/etc/logrotate.d/design-library`. Logs in `logs/` are rotated by the system logrotate service.

### Reload after service file changes

After editing `.service` files, reload systemd and restart:

```bash
sudo systemctl daemon-reload
sudo systemctl restart design-library-watcher
sudo systemctl restart design-library-reindex.timer
```

### Enable/disable on boot

```bash
# Enable
sudo systemctl enable design-library-watcher
sudo systemctl enable design-library-reindex.timer

# Disable
sudo systemctl disable design-library-watcher
sudo systemctl disable design-library-reindex.timer
```

## Index Statistics

```bash
cd /home/rpi/ai-engine/design-library-indexer
/home/rpi/ai-engine/venv/bin/python run_indexer.py stats
```

## Reset Index

```bash
cd /home/rpi/ai-engine/design-library-indexer
/home/rpi/ai-engine/venv/bin/python run_indexer.py reset
```

## Monitoring

```bash
# Watch indexing logs
tail -f /home/rpi/ai-engine/logs/indexer-manual.log

# Watch auto-tuning decisions
tail -f /home/rpi/ai-engine/logs/indexer-manual.log | grep "Auto-tune"

# Watch file watcher
tail -f /home/rpi/ai-engine/logs/watcher.log

# Watch RAG API
tail -f /home/rpi/ai-engine/logs/rag-api.log

# Check RAG API health
curl -s http://localhost:8000/health | python3 -m json.tool

# System health
vcgencmd measure_temp
free -h
uptime
```

## Logs

| File | Purpose |
|------|---------|
| `logs/indexer-manual.log` | Manual indexing and search |
| `logs/watcher.log` | File watcher output |
| `logs/watcher-error.log` | File watcher errors |
| `logs/reindex.log` | Nightly re-index |
| `logs/reindex-error.log` | Nightly re-index errors |
| `logs/rag-api.log` | RAG API server |

## Directory Structure

```
/home/rpi/ai-engine/
├── setup.sh                    # One-time setup script (Pi 4)
├── design-library-indexer/     # Indexer application (GitHub repo)
│   ├── indexer/                # Python modules
│   │   ├── autotune.py        # Adaptive worker auto-tuning
│   │   ├── chunker.py         # Code splitting
│   │   ├── config.py          # Configuration
│   │   ├── discovery.py       # File scanning
│   │   ├── embeddings.py      # Ollama client
│   │   ├── engine.py          # Pipeline orchestration
│   │   └── store.py           # ChromaDB interface
│   ├── setup-ai-process/      # Service files, nginx config, setup script
│   ├── run_indexer.py         # CLI entry point
│   └── watch_library.py       # File watcher
├── rag-api/                    # RAG API server
│   ├── main.py                # FastAPI app with all endpoints
│   ├── llm.py                 # Ollama chat client (qwen2.5-coder:3b)
│   ├── prompts.py             # System prompts + design rules
│   ├── seo.py                 # SEO audit logic (BeautifulSoup)
│   └── test_pipeline.py       # End-to-end test
├── frontend/                   # Web UI (static HTML/CSS/JS)
│   ├── index.html             # SPA with 4 tabs
│   ├── css/style.css          # Dark theme styles
│   └── js/app.js              # Frontend logic
├── mcp-server/                 # MCP server for IDE integration
│   └── server.py              # 5 tools via stdio transport
├── docs/                       # Documentation
│   ├── rag-api.md             # RAG API reference
│   ├── frontend.md            # Frontend setup guide
│   └── mcp-server.md          # MCP server setup guide
├── venv/                       # Python virtual environment
├── chroma_data/                # Vector database
├── logs/                       # Application logs
└── search.sh                   # Quick search helper

/mnt/design-library/            # Your design files (USB SSD)
└── .index/file_hashes.json     # Change tracking
```

## Search Quality Tuning

### Head-meta filtering

HTML `<head>` boilerplate is indexed with `section_type="head-meta"` and **excluded from search results by default**. This prevents meta tags from dominating results at ~0.45 similarity. Use `--include-head` to include them when specifically searching for SEO/meta content.

### Chunk size tuning

Adjust `chunk_target_chars` in `indexer/config.py` to control granularity:
- **Smaller** (e.g. 500) = more granular search, slower indexing
- **Larger** (e.g. 1500) = faster indexing, broader matches
- **Default**: 1000

After changing config, run a full re-index:

```bash
cd /home/rpi/ai-engine/design-library-indexer
pkill -f "run_indexer.py"
nohup /home/rpi/ai-engine/venv/bin/python run_indexer.py index --full -v \
  > /home/rpi/ai-engine/logs/full-index-$(date +%Y%m%d-%H%M%S).log 2>&1 &
```

### Adding new repos

Drop git repos into `/mnt/design-library/example-websites/` — the watcher detects new files automatically (30s debounce). No manual re-index needed.

## Key Features

- **Semantic search** - Find code by describing what you want
- **RAG code generation** - Generate UI code using design library context
- **Web UI** - Browser-based interface accessible from any device on LAN
- **MCP IDE integration** - Use RAG tools directly in Claude Code / VS Code
- **SEO audit** - Score HTML against 11 SEO rules
- **Head-meta filtering** - Excludes HTML `<head>` boilerplate from search results by default
- **Adaptive worker auto-tuning** - 40-70% faster indexing based on CPU/RAM/temperature
- **Incremental indexing** - Only processes new or changed files
- **Resume support** - Stop and restart anytime without losing progress
- **Thermal protection** - Automatically reduces load when Pi gets hot
- **Framework detection** - Categorizes React, Vue, Next.js, Astro, Svelte, etc.
- **Real-time watching** - Auto-indexes files as you add them

## Documentation

- [docs/rag-api.md](docs/rag-api.md) - RAG API endpoints, schemas, and examples
- [docs/frontend.md](docs/frontend.md) - Web UI setup and nginx configuration
- [docs/mcp-server.md](docs/mcp-server.md) - MCP server setup and tool reference
- [docs/README.md](design-library-indexer/docs/README.md) - Comprehensive indexer guide
- [docs/adaptive_workers.md](design-library-indexer/docs/adaptive_workers.md) - Auto-tuning guide
- [docs/design_decisions.md](design-library-indexer/docs/design_decisions.md) - Architecture decisions
- [docs/implementation_summary.md](design-library-indexer/docs/implementation_summary.md) - Quick reference

## Tech Stack

- **Raspberry Pi 4** - Hardware platform
- **Ollama** - Local LLM (qwen2.5-coder:3b) and embeddings (nomic-embed-text, 768-dim)
- **ChromaDB** - Vector database
- **FastAPI** - RAG API server
- **nginx** - Reverse proxy and static file server
- **MCP SDK** - Model Context Protocol for IDE integration
- **BeautifulSoup** - SEO audit HTML parsing
- **Python 3.12** - Application code
- **systemd** - Service management
