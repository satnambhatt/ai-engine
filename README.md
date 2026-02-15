# AI Engine

AI-powered semantic search for web design files running on Raspberry Pi 5.

## What It Does

Indexes your design library (HTML, CSS, JS, React, Vue, etc.) into a vector database so you can search by describing what you want instead of remembering file names.

```bash
# Find code by description
./search.sh "hero section with gradient background"
./search.sh "responsive navigation with dropdown"
./search.sh "animated loading spinner"
./search.sh "pricing table with three columns"
```

## Quick Start

### 1. Setup (first time only)

```bash
cd /home/rpi/ai-engine/design-library-indexer
chmod +x setup.sh
sudo ./setup.sh
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

## Directory Structure

```
/home/rpi/ai-engine/
├── design-library-indexer/     # Main application (GitHub repo)
│   ├── indexer/                # Python modules
│   │   ├── autotune.py        # Adaptive worker auto-tuning
│   │   ├── chunker.py         # Code splitting
│   │   ├── config.py          # Configuration
│   │   ├── discovery.py       # File scanning
│   │   ├── embeddings.py      # Ollama client
│   │   ├── engine.py          # Pipeline orchestration
│   │   └── store.py           # ChromaDB interface
│   ├── setup-ai-process/      # Service files and setup
│   ├── docs/                  # Documentation
│   ├── run_indexer.py         # CLI entry point
│   └── watch_library.py       # File watcher
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
- **Head-meta filtering** - Excludes HTML `<head>` boilerplate from search results by default
- **Adaptive worker auto-tuning** - 40-70% faster indexing based on CPU/RAM/temperature
- **Incremental indexing** - Only processes new or changed files
- **Resume support** - Stop and restart anytime without losing progress
- **Thermal protection** - Automatically reduces load when Pi gets hot
- **Framework detection** - Categorizes React, Vue, Next.js, Astro, Svelte, etc.
- **Real-time watching** - Auto-indexes files as you add them

## Documentation

- [docs/README.md](design-library-indexer/docs/README.md) - Comprehensive system guide
- [docs/adaptive_workers.md](design-library-indexer/docs/adaptive_workers.md) - Auto-tuning guide
- [docs/design_decisions.md](design-library-indexer/docs/design_decisions.md) - Architecture decisions
- [docs/implementation_summary.md](design-library-indexer/docs/implementation_summary.md) - Quick reference

## Tech Stack

- **Raspberry Pi 5** - Hardware platform
- **Ollama** - Local AI (nomic-embed-text, 768-dim embeddings)
- **ChromaDB** - Vector database
- **Python 3** - Application code
- **systemd** - Service management
