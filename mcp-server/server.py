#!/usr/bin/env python3
"""
MCP Server for the Design Library RAG API.

Exposes search, code generation, templates, SEO audit, and health check
as MCP tools that Claude Code / VS Code can call directly from the IDE.

Usage:
    /home/rpi/ai-engine/venv/bin/python /home/rpi/ai-engine/mcp-server/server.py

Configure in ~/.claude.json:
    {
      "mcpServers": {
        "design-rag": {
          "type": "stdio",
          "command": "/home/rpi/ai-engine/venv/bin/python",
          "args": ["/home/rpi/ai-engine/mcp-server/server.py"]
        }
      }
    }
"""

import json
import logging
import sys
from contextlib import asynccontextmanager
from dataclasses import dataclass

import httpx
from mcp.server.fastmcp import FastMCP

# ── Logging (stderr only — stdout is reserved for MCP protocol) ──────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.StreamHandler(sys.stderr)],
)
logger = logging.getLogger("design-rag-mcp")

# ── Configuration ────────────────────────────────────────────────────
RAG_API_BASE = "http://localhost:8000"
SEARCH_TIMEOUT = 30.0
GENERATE_TIMEOUT = 660.0  # 11 min — LLM generation takes 2-10 min on Pi


# ── Lifespan — shared HTTP client ────────────────────────────────────
@dataclass
class AppContext:
    http: httpx.AsyncClient


@asynccontextmanager
async def app_lifespan(server):
    """Create a shared async HTTP client for the server lifetime."""
    async with httpx.AsyncClient(base_url=RAG_API_BASE) as client:
        logger.info(f"MCP server started — RAG API: {RAG_API_BASE}")
        yield AppContext(http=client)
    logger.info("MCP server shutting down")


# ── Server instance ──────────────────────────────────────────────────
mcp = FastMCP(
    name="design-rag",
    instructions="Design system RAG tools — semantic search, code generation, SEO audit",
    lifespan=app_lifespan,
)


# ── Helper ───────────────────────────────────────────────────────────
def _get_http() -> httpx.AsyncClient:
    """Get the shared HTTP client from the lifespan context."""
    ctx = mcp.get_context()
    return ctx.request_context.lifespan_context.http


# ── Tools ────────────────────────────────────────────────────────────

@mcp.tool()
async def search_design_library(
    query: str,
    framework: str | None = None,
    category: str | None = None,
    n_results: int = 5,
) -> str:
    """Search the design system library using semantic similarity.

    Returns matching code snippets from the indexed design library (HTML, React,
    Vue, CSS, Astro, Svelte). Use this to find existing design patterns, components,
    and layouts.

    Args:
        query: Natural language search query (e.g. "responsive navbar with dropdown",
               "hero section with gradient background", "pricing table with toggle")
        framework: Filter results by framework: "html", "react", "vue", "svelte",
                   "astro", "css". Leave empty for all frameworks.
        category: Filter by component category: "hero", "header", "footer",
                  "navigation", "card", "pricing", "testimonial", "contact",
                  "cta", "faq", "form", "table", "gallery", "modal", "sidebar", "404".
                  Leave empty for all categories.
        n_results: Number of results to return (1-20, default 5)
    """
    http = _get_http()
    body = {"query": query, "n_results": min(max(n_results, 1), 20)}
    if framework:
        body["framework"] = framework
    if category:
        body["category"] = category

    try:
        resp = await http.post("/search", json=body, timeout=SEARCH_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()

        # Format for readability
        results = data.get("results", [])
        if not results:
            return f"No results found for: {query}"

        lines = [f"Found {len(results)} results for \"{query}\" ({data['duration_ms']}ms):\n"]
        for i, r in enumerate(results, 1):
            lines.append(f"--- Result {i}: {r['file_path']} ({r['framework']}, {r['similarity']:.0%} match) ---")
            lines.append(r["text"])
            lines.append("")

        return "\n".join(lines)
    except httpx.HTTPStatusError as e:
        return f"Error: API returned {e.response.status_code} — {e.response.text}"
    except httpx.TimeoutException:
        return "Error: Search request timed out"
    except httpx.ConnectError:
        return "Error: Cannot connect to RAG API at localhost:8000. Is the server running?"
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
async def generate_code(
    brief: str,
    task: str = "component",
    framework: str | None = None,
    n_context: int = 3,
) -> str:
    """Generate UI code using RAG-augmented context from the design library.

    Searches the design library for relevant examples, injects them as context,
    and generates production-ready HTML/CSS code using a local LLM.

    NOTE: Generation takes 2-10 minutes on Raspberry Pi. Be patient.

    Args:
        brief: Description of what to build (e.g. "a pricing page with 3 tiers
               and a monthly/yearly toggle", "a SaaS hero section with signup CTA")
        task: Task type — "hero" (hero section), "page" (full HTML page),
              "component" (reusable UI component), "seo_rewrite" (fix SEO issues
              in provided HTML). Default: "component"
        framework: Filter RAG context by framework: "html", "react", "vue", "css".
                   Leave empty to use all available context.
        n_context: Number of design library examples to use as context (0-10,
                   default 3). Use 0 for raw LLM generation without examples.
    """
    http = _get_http()
    body = {"brief": brief, "task": task, "n_context": min(max(n_context, 0), 10)}
    if framework:
        body["framework"] = framework

    try:
        resp = await http.post("/generate", json=body, timeout=GENERATE_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()

        lines = [
            f"Generated {task} ({data['model']}, {data['duration_ms'] / 1000:.1f}s):\n",
            data["code"],
        ]

        if data.get("context_used"):
            lines.append(f"\n--- Context used ({len(data['context_used'])} chunks) ---")
            for c in data["context_used"]:
                lines.append(f"  - {c['file_path']} ({c['similarity']:.0%} match)")

        return "\n".join(lines)
    except httpx.HTTPStatusError as e:
        return f"Error: API returned {e.response.status_code} — {e.response.text}"
    except httpx.TimeoutException:
        return "Error: Generation timed out (>10 minutes). Try a simpler brief or reduce n_context."
    except httpx.ConnectError:
        return "Error: Cannot connect to RAG API at localhost:8000. Is the server running?"
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
async def list_templates(category: str) -> str:
    """List available design templates from the indexed library by category.

    Returns templates with their file paths, frameworks, and code previews.

    Args:
        category: Template category. One of: "hero", "header", "footer",
                  "navigation", "card", "pricing", "testimonial", "contact",
                  "cta", "faq", "form", "table", "gallery", "modal",
                  "sidebar", "404"
    """
    http = _get_http()
    try:
        resp = await http.get(f"/templates/{category}", timeout=SEARCH_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()

        templates = data.get("templates", [])
        if not templates:
            return f"No templates found for category: {category}"

        lines = [f"Found {data['count']} {category} templates:\n"]
        for i, t in enumerate(templates, 1):
            lines.append(f"[{i}] {t['file_path']} ({t['framework']})")
            lines.append(f"    Preview: {t['preview'][:120]}...")
            lines.append("")

        return "\n".join(lines)
    except httpx.HTTPStatusError as e:
        return f"Error: API returned {e.response.status_code} — {e.response.text}"
    except httpx.TimeoutException:
        return "Error: Templates request timed out"
    except httpx.ConnectError:
        return "Error: Cannot connect to RAG API at localhost:8000. Is the server running?"
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
async def seo_audit(html: str) -> str:
    """Audit HTML content for SEO best practices.

    Checks for common SEO issues: title tag, meta description, H1 tags,
    heading hierarchy, viewport meta, Open Graph tags, canonical URL, image
    alt text, and more. Returns a score out of 100 with detailed findings.

    Args:
        html: The HTML string to audit. Can be a full page or a partial snippet.
    """
    http = _get_http()
    try:
        resp = await http.post("/seo/audit", json={"html": html}, timeout=10.0)
        resp.raise_for_status()
        data = resp.json()

        lines = [f"SEO Score: {data['score']}/100\n"]
        lines.append(f"Passed: {data['passed_count']} | Errors: {data['errors']} | Warnings: {data['warnings']}\n")

        if data.get("issues"):
            lines.append("Issues:")
            for i in data["issues"]:
                icon = "ERROR" if i["severity"] == "error" else "WARN"
                lines.append(f"  [{icon}] {i['message']}")

        if data.get("passed"):
            lines.append("\nPassed:")
            for p in data["passed"]:
                lines.append(f"  [PASS] {p['message']}")

        return "\n".join(lines)
    except httpx.HTTPStatusError as e:
        return f"Error: API returned {e.response.status_code} — {e.response.text}"
    except httpx.ConnectError:
        return "Error: Cannot connect to RAG API at localhost:8000. Is the server running?"
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
async def health_check() -> str:
    """Check the health of the Design Library RAG system.

    Returns the status of the embedding model, chat model, ChromaDB vector
    database, and the number of indexed design chunks.
    """
    http = _get_http()
    try:
        resp = await http.get("/health", timeout=10.0)
        resp.raise_for_status()
        data = resp.json()

        return (
            f"Status: {data['status']}\n"
            f"Embedding model (nomic-embed-text): {'OK' if data['ollama_embed'] else 'DOWN'}\n"
            f"Chat model (qwen2.5-coder:3b): {'OK' if data['ollama_chat'] else 'DOWN'}\n"
            f"ChromaDB: {'OK' if data['chromadb'] else 'DOWN'}\n"
            f"Chunks indexed: {data['chunks_indexed']:,}"
        )
    except httpx.ConnectError:
        return "Error: Cannot connect to RAG API at localhost:8000. Is the server running?"
    except Exception as e:
        return f"Error: {e}"


# ── Entrypoint ───────────────────────────────────────────────────────
if __name__ == "__main__":
    mcp.run(transport="stdio")
