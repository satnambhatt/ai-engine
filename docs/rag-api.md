# RAG API - Design Library Code Generation

FastAPI service that combines semantic search with LLM code generation.
Search your design library and generate production-ready code from natural language briefs.

## How It Works

```
Brief ("hero section for SaaS landing page")
  │
  ▼
1. Embed brief → 768-dim vector (nomic-embed-text)
  │
  ▼
2. Search ChromaDB → top N relevant design examples
  │
  ▼
3. Build prompt → system prompt + design rules + context + brief
  │
  ▼
4. Generate code → qwen2.5-coder:3b via Ollama
  │
  ▼
5. Return generated HTML/CSS code
```

## Quick Start

### Start the server

```bash
cd /home/rpi/ai-engine/rag-api
/home/rpi/ai-engine/venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000
```

### Start in background

```bash
cd /home/rpi/ai-engine/rag-api
nohup /home/rpi/ai-engine/venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000 \
  > /home/rpi/ai-engine/logs/rag-api.log 2>&1 &
```

### Health check

```bash
curl http://localhost:8000/health
```

```json
{
  "status": "ok",
  "ollama_embed": true,
  "ollama_chat": true,
  "chromadb": true,
  "chunks_indexed": 5331
}
```

## Endpoints

### POST /search

Semantic search across the indexed design library.

```bash
curl -X POST http://localhost:8000/search \
  -H "Content-Type: application/json" \
  -d '{"query": "hero section with gradient", "n_results": 3}'
```

**Request body:**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `query` | string | required | Natural language search query |
| `framework` | string | null | Filter: html, react, css, astro, vue, etc. |
| `category` | string | null | Filter: hero, header, footer, pricing, etc. |
| `n_results` | int | 5 | Number of results (1-50) |
| `include_head` | bool | false | Include `<head>` meta chunks |

**Response:**

```json
{
  "query": "hero section with gradient",
  "results": [
    {
      "file_path": "example-websites/tailwind/hyperui/public/components/marketing/banners/3.html",
      "text": "<section class=\"hero\">...</section>",
      "similarity": 0.653,
      "framework": "html",
      "component_category": "hero",
      "section_type": "section-part",
      "repo_name": "hyperui"
    }
  ],
  "duration_ms": 8498
}
```

### POST /generate

Generate code using the RAG pipeline. Searches for relevant examples, injects them as context, and generates code with the LLM.

```bash
curl -X POST http://localhost:8000/generate \
  -H "Content-Type: application/json" \
  -d '{
    "brief": "A hero section for a SaaS landing page with a signup CTA button",
    "task": "hero",
    "framework": "html",
    "n_context": 3
  }'
```

**Request body:**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `brief` | string | required | Description of what to generate |
| `task` | string | "component" | Task type (see below) |
| `framework` | string | null | Filter RAG context by framework |
| `n_context` | int | 3 | Number of context chunks to inject (0-10) |
| `temperature` | float | 0.7 | LLM creativity (0.0=deterministic, 1.0=creative) |

**Task types:**

| Task | Description |
|------|-------------|
| `hero` | Hero section with headline, subheadline, CTA |
| `page` | Full HTML page with head, header, main, footer |
| `component` | Reusable UI component (card, form, nav, etc.) |
| `seo_rewrite` | Rewrite HTML to fix SEO issues |

**Response:**

```json
{
  "code": "<section class=\"hero\">...</section>",
  "context_used": [
    {
      "text": "...",
      "file_path": "example-websites/...",
      "similarity": 0.65,
      "framework": "html"
    }
  ],
  "model": "qwen2.5-coder:3b",
  "duration_ms": 45000,
  "task": "hero"
}
```

**Note:** Generation takes 2-10 minutes on Raspberry Pi depending on output length.

### GET /templates/{category}

List available templates from the design library by component category.

```bash
curl http://localhost:8000/templates/hero
curl http://localhost:8000/templates/pricing
curl http://localhost:8000/templates/footer
```

**Valid categories:** hero, header, footer, pricing, testimonial, contact, cta, faq, 404, sidebar, table, form, navigation, card, gallery, modal

**Response:**

```json
{
  "category": "hero",
  "count": 6,
  "templates": [
    {
      "file_path": "example-websites/react/open-react-template/components/hero-home.tsx",
      "framework": "react",
      "repo_name": "open-react-template",
      "preview": "<section class=\"hero\">..."
    }
  ]
}
```

### POST /seo/audit

Run an SEO audit on HTML content. Pure rule-based analysis (no LLM).

```bash
curl -X POST http://localhost:8000/seo/audit \
  -H "Content-Type: application/json" \
  --data-raw '{"html":"<html><head><title>Test</title></head><body><h1>Hello</h1></body></html>"}'
```

**Response:**

```json
{
  "score": 50,
  "total_checks": 9,
  "errors": 2,
  "warnings": 6,
  "passed_count": 1,
  "issues": [
    {"severity": "error", "rule": "missing_meta_description", "message": "..."},
    {"severity": "warning", "rule": "missing_lang", "message": "..."}
  ],
  "passed": [
    {"rule": "has_h1", "message": "Page has exactly one <h1> tag"}
  ]
}
```

**SEO rules checked:**
- Title tag exists (30-60 chars)
- Meta description (120-160 chars)
- Exactly one H1 tag
- HTML lang attribute
- Charset declaration
- Viewport meta (mobile-friendly)
- Image alt attributes
- Heading hierarchy (no skipping levels)
- Open Graph tags (og:title, og:description)
- Canonical URL
- Empty links

## Prompt Engineering

### Design rules

Every generation prompt includes design rules that enforce quality:

- Semantic HTML5 elements
- Mobile-first responsive design
- CSS custom properties for theming
- Accessible markup (alt text, ARIA labels)
- No generic AI aesthetics (no excessive gradients, no Lorem ipsum)
- Clean, minimal markup
- Proper hover/focus states

### Context injection

The RAG pipeline injects relevant code examples from your design library into the prompt. The LLM uses these as inspiration while generating original code based on your brief.

```
System prompt (task-specific rules + design guidelines)
  +
Context chunks (top N similar code from ChromaDB)
  +
User brief ("A hero section for a SaaS landing page")
  =
Complete prompt sent to qwen2.5-coder:3b
```

### Customizing prompts

Edit `/home/rpi/ai-engine/rag-api/prompts.py` to:
- Modify system prompts per task type
- Update design rules
- Add new task types

## Testing

### Run end-to-end test

```bash
cd /home/rpi/ai-engine/rag-api
/home/rpi/ai-engine/venv/bin/python test_pipeline.py
```

Tests the full pipeline: embed -> search -> prompt build -> generate -> SEO audit.

### Test individual endpoints

```bash
# Health
curl http://localhost:8000/health

# Search
curl -X POST http://localhost:8000/search \
  -H "Content-Type: application/json" \
  -d '{"query": "responsive navigation menu"}'

# Generate (takes 2-10 min on Pi)
curl -X POST http://localhost:8000/generate \
  -H "Content-Type: application/json" \
  -d '{"brief": "A pricing table with monthly and yearly toggle", "task": "component"}'

# Templates
curl http://localhost:8000/templates/hero

# SEO audit
curl -X POST http://localhost:8000/seo/audit \
  -H "Content-Type: application/json" \
  --data-raw '{"html":"<html><body><h1>Test</h1></body></html>"}'
```

### Interactive API docs

When the server is running, visit:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## Configuration

### Environment

The API reads configuration from `IndexerConfig` defaults:

| Setting | Default | Description |
|---------|---------|-------------|
| Ollama URL | http://localhost:11434 | Ollama API endpoint |
| Embedding model | nomic-embed-text | 768-dim embeddings |
| Chat model | qwen2.5-coder:3b | Code generation LLM |
| ChromaDB path | /home/rpi/ai-engine/chroma_data | Vector database |
| API port | 8000 | FastAPI server port |
| LLM timeout | 600s | Max generation time |

### Performance on Raspberry Pi

| Operation | Time | Notes |
|-----------|------|-------|
| Search | 2-8 seconds | Embed query + ChromaDB lookup |
| Generate (hero) | 2-5 minutes | Depends on output length |
| Generate (full page) | 5-10 minutes | Larger output |
| SEO audit | < 100ms | No LLM, pure HTML parsing |
| Templates | 2-8 seconds | Embed + search |

### Remote Ollama (faster generation)

For faster generation, point to a desktop PC with GPU:

```bash
# On desktop with GPU
ollama serve --host 0.0.0.0:11434

# Update config in rag-api/main.py or use environment
# config.ollama_base_url = "http://192.168.1.100:11434"
```

## File Structure

```
/home/rpi/ai-engine/rag-api/
├── main.py              # FastAPI app with all endpoints
├── llm.py               # Ollama chat client wrapper
├── prompts.py           # System prompts + design rules
├── seo.py               # SEO audit logic (BeautifulSoup)
├── requirements.txt     # fastapi, uvicorn, beautifulsoup4
└── test_pipeline.py     # End-to-end test script
```

## Dependencies

New dependencies (added to existing venv):
- `fastapi` - Web framework
- `uvicorn` - ASGI server
- `beautifulsoup4` - HTML parsing for SEO audit

Reused from indexer:
- `chromadb` - Vector database
- `requests` - HTTP client for Ollama
- `psutil` - System metrics

## Stopping the Server

```bash
pkill -f "uvicorn main:app"
```

---

**Last Updated:** February 16, 2026
**Status:** Production Ready
