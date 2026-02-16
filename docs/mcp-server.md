# MCP Server — Design Library RAG Tools for IDE

Model Context Protocol (MCP) server that exposes the RAG API tools directly in your IDE (Claude Code, VS Code).

## How It Works

```
IDE (Claude Code / VS Code)
    │ stdio
    ▼
MCP Server (server.py)
    │ httpx
    ▼
RAG API (localhost:8000)
    │
    ▼
ChromaDB + Ollama
```

The MCP server runs as a subprocess spawned by your IDE. It communicates over stdin/stdout using the MCP JSON-RPC protocol. Internally, it calls the RAG API via HTTP.

## Setup

### 1. Install dependencies

Dependencies are already installed in the shared venv:

```bash
/home/rpi/ai-engine/venv/bin/pip install "mcp[cli]" httpx
```

### 2. Ensure the RAG API is running

```bash
cd /home/rpi/ai-engine/rag-api
nohup /home/rpi/ai-engine/venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000 \
  > /home/rpi/ai-engine/logs/rag-api.log 2>&1 &
```

### 3. Configure your IDE

#### Claude Code

Add to `~/.claude.json`:

```json
{
  "mcpServers": {
    "design-rag": {
      "type": "stdio",
      "command": "/home/rpi/ai-engine/venv/bin/python",
      "args": ["/home/rpi/ai-engine/mcp-server/server.py"]
    }
  }
}
```

Or use the CLI:

```bash
claude mcp add design-rag -- /home/rpi/ai-engine/venv/bin/python /home/rpi/ai-engine/mcp-server/server.py
```

Then restart Claude Code. Verify with:

```bash
claude mcp list
```

#### VS Code

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

Or use the command palette: `Ctrl+Shift+P` > "MCP: Add Server" > stdio.

## Available Tools

### search_design_library

Search the design library using semantic similarity.

**Parameters:**

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `query` | string | required | Natural language search query |
| `framework` | string | null | Filter: html, react, vue, svelte, astro, css |
| `category` | string | null | Filter: hero, header, footer, navigation, card, pricing, etc. |
| `n_results` | int | 5 | Number of results (1-20) |

**Example usage in Claude Code:**
> "Search the design library for responsive navigation menus in React"

### generate_code

Generate UI code using RAG-augmented context.

**Parameters:**

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `brief` | string | required | Description of what to build |
| `task` | string | "component" | hero, page, component, seo_rewrite |
| `framework` | string | null | Filter context by framework |
| `n_context` | int | 3 | Number of context chunks (0-10) |

**Example usage in Claude Code:**
> "Generate a pricing table with monthly/yearly toggle using the design library"

**Note:** Takes 2-10 minutes on Raspberry Pi.

### list_templates

Browse available templates by category.

**Parameters:**

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `category` | string | required | hero, header, footer, navigation, card, pricing, testimonial, contact, cta, faq, form, table, gallery, modal, sidebar, 404 |

**Example usage in Claude Code:**
> "List all hero templates from the design library"

### seo_audit

Audit HTML for SEO best practices.

**Parameters:**

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `html` | string | required | HTML content to audit |

**Example usage in Claude Code:**
> "Run an SEO audit on this HTML: <html>..."

### health_check

Check the RAG system status.

**Example usage in Claude Code:**
> "Check the design library RAG health"

## File Structure

```
/home/rpi/ai-engine/mcp-server/
├── server.py           # MCP server with 5 tools
└── requirements.txt    # mcp[cli], httpx
```

## Testing

### Interactive testing with MCP dev tools

```bash
/home/rpi/ai-engine/venv/bin/python -m mcp dev /home/rpi/ai-engine/mcp-server/server.py
```

### Manual protocol test

```bash
printf '{"jsonrpc":"2.0","method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}},"id":1}\n{"jsonrpc":"2.0","method":"notifications/initialized","params":{}}\n{"jsonrpc":"2.0","method":"tools/list","id":2}\n' | /home/rpi/ai-engine/venv/bin/python /home/rpi/ai-engine/mcp-server/server.py 2>/dev/null
```

## Troubleshooting

**Tools don't appear in IDE:**
- Restart the IDE after adding the MCP config
- Verify the Python path is correct: `/home/rpi/ai-engine/venv/bin/python`
- Check the server starts: run `server.py` manually and look for errors on stderr

**"Cannot connect to RAG API":**
- Start the RAG API: see step 2 above
- Verify: `curl http://localhost:8000/health`

**Generation times out:**
- The generate_code tool has an 11-minute timeout
- If it still times out, try a simpler brief or reduce n_context

**Import errors:**
- Ensure `mcp` and `httpx` are installed in the venv:
  ```bash
  /home/rpi/ai-engine/venv/bin/pip install "mcp[cli]" httpx
  ```

---

**Last Updated:** February 16, 2026
