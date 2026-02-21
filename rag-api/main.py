"""
RAG API — FastAPI application for design library search and code generation.

Endpoints:
    POST /search         — Semantic search across the design library
    POST /generate       — RAG-powered code generation from a brief
    GET  /templates/{category} — List available templates by category
    POST /seo/audit      — SEO audit on HTML content
    GET  /health         — Health check
"""

import logging
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# Add the indexer package to the Python path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "design-library-indexer"))

from indexer.config import IndexerConfig
from indexer.embeddings import EmbeddingClient
from indexer.store import VectorStore

from llm import OllamaChat
from prompts import build_prompt
from seo import audit_html

logger = logging.getLogger(__name__)

# ── Logging setup ────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(levelname)-7s │ %(name)s │ %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logging.getLogger("chromadb").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)


# ── Request/Response Models ──────────────────────────────────────────────────

class SearchRequest(BaseModel):
    query: str = Field(..., description="Natural language search query")
    framework: str | None = Field(None, description="Filter by framework (html, react, css, etc.)")
    category: str | None = Field(None, description="Filter by component category (hero, header, etc.)")
    n_results: int = Field(5, ge=1, le=50, description="Number of results to return")
    include_head: bool = Field(False, description="Include <head> meta chunks in results")


class SearchResultItem(BaseModel):
    file_path: str
    text: str
    similarity: float
    framework: str
    component_category: str
    section_type: str
    repo_name: str


class SearchResponse(BaseModel):
    query: str
    results: list[SearchResultItem]
    duration_ms: int


class HistoryMessage(BaseModel):
    role: str = Field(..., description="'user' or 'assistant'")
    content: str = Field(..., description="Message content")


class GenerateRequest(BaseModel):
    brief: str = Field(..., description="Description of what to generate")
    task: str = Field("component", description="Task type: hero, page, component, seo_rewrite")
    framework: str | None = Field(None, description="Filter RAG context by framework")
    n_context: int = Field(3, ge=0, le=10, description="Number of RAG context chunks to use")
    temperature: float = Field(0.7, ge=0.0, le=1.0, description="LLM sampling temperature")
    history: list[HistoryMessage] = Field(default_factory=list, description="Prior conversation turns for multi-turn refinement")


class GenerateResponse(BaseModel):
    code: str
    context_used: list[dict]
    model: str
    duration_ms: int
    task: str
    history: list[HistoryMessage] = Field(description="Updated conversation history — pass this back in the next request")


class TemplateItem(BaseModel):
    file_path: str
    framework: str
    repo_name: str
    preview: str
    text: str


class TemplatesResponse(BaseModel):
    category: str
    count: int
    templates: list[TemplateItem]


class SEOAuditRequest(BaseModel):
    html: str = Field(..., description="HTML content to audit")


class HealthResponse(BaseModel):
    status: str
    ollama_embed: bool
    ollama_chat: bool
    chromadb: bool
    chunks_indexed: int


# ── App State ────────────────────────────────────────────────────────────────

VALID_TASKS = {"hero", "page", "component", "seo_rewrite"}
VALID_CATEGORIES = {
    "hero", "header", "footer", "pricing", "testimonial",
    "contact", "cta", "faq", "404", "sidebar", "table", "form",
    "navigation", "card", "gallery", "modal",
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize shared resources on startup."""
    logger.info("Starting RAG API...")

    config = IndexerConfig()
    embedder = EmbeddingClient(config)
    store = VectorStore(config)
    chat = OllamaChat(
        base_url=config.ollama_base_url,
        model="qwen2.5-coder:3b",
    )

    # Health checks
    embed_ok = embedder.health_check()
    chat_ok = chat.health_check()
    if not embed_ok:
        logger.warning("Embedding model not available — search will fail")
    if not chat_ok:
        logger.warning("Chat model not available — generation will fail")

    store.initialize()
    stats = store.get_stats()
    logger.info(f"ChromaDB ready: {stats['total_chunks']} chunks indexed")

    # Store on app state
    app.state.config = config
    app.state.embedder = embedder
    app.state.store = store
    app.state.chat = chat

    logger.info("RAG API ready")
    yield

    logger.info("Shutting down RAG API")


app = FastAPI(
    title="Design Library RAG API",
    description="Semantic search and AI code generation powered by your design library",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Endpoints ────────────────────────────────────────────────────────────────

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Check system health."""
    embedder: EmbeddingClient = app.state.embedder
    store: VectorStore = app.state.store
    chat: OllamaChat = app.state.chat

    embed_ok = embedder.health_check()
    chat_ok = chat.health_check()
    stats = store.get_stats()

    return HealthResponse(
        status="ok" if embed_ok and chat_ok else "degraded",
        ollama_embed=embed_ok,
        ollama_chat=chat_ok,
        chromadb=True,
        chunks_indexed=stats["total_chunks"],
    )


@app.post("/search", response_model=SearchResponse)
async def search(req: SearchRequest):
    """Semantic search across the design library."""
    embedder: EmbeddingClient = app.state.embedder
    store: VectorStore = app.state.store

    start = time.monotonic()

    # Embed the query
    embed_result = embedder.embed(req.query)
    if embed_result is None:
        raise HTTPException(status_code=502, detail="Failed to embed search query")

    # Search ChromaDB
    exclude_sections = None if req.include_head else ["head-meta"]
    results = store.search(
        query_embedding=embed_result.embedding,
        n_results=req.n_results,
        framework=req.framework,
        component_category=req.category,
        exclude_sections=exclude_sections,
    )

    duration_ms = int((time.monotonic() - start) * 1000)

    return SearchResponse(
        query=req.query,
        results=[
            SearchResultItem(
                file_path=r.file_path,
                text=r.text,
                similarity=round(1 - r.distance, 3),
                framework=r.framework,
                component_category=r.component_category or "",
                section_type=r.section_type,
                repo_name=r.repo_name or "",
            )
            for r in results
        ],
        duration_ms=duration_ms,
    )


@app.post("/generate", response_model=GenerateResponse)
async def generate(req: GenerateRequest):
    """Generate code using RAG pipeline: brief -> search -> LLM -> code."""
    embedder: EmbeddingClient = app.state.embedder
    store: VectorStore = app.state.store
    chat: OllamaChat = app.state.chat

    if req.task not in VALID_TASKS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid task '{req.task}'. Valid: {sorted(VALID_TASKS)}",
        )

    start = time.monotonic()

    # Step 1: Embed the brief for RAG context retrieval
    context_chunks = []
    if req.n_context > 0:
        embed_result = embedder.embed(req.brief)
        if embed_result is None:
            raise HTTPException(status_code=502, detail="Failed to embed brief for context retrieval")

        # Step 2: Search ChromaDB for relevant design examples
        results = store.search(
            query_embedding=embed_result.embedding,
            n_results=req.n_context,
            framework=req.framework,
            exclude_sections=["head-meta"],
        )

        context_chunks = [
            {
                "text": r.text,
                "file_path": r.file_path,
                "similarity": round(1 - r.distance, 3),
                "framework": r.framework,
            }
            for r in results
        ]

    # Step 3: Build prompt with context injection
    system_prompt, user_prompt = build_prompt(
        task=req.task,
        brief=req.brief,
        context_chunks=context_chunks,
    )

    # Step 4: Generate code with LLM (inject prior conversation history)
    llm_result = chat.generate(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        temperature=req.temperature,
        history=[{"role": m.role, "content": m.content} for m in req.history],
    )

    if llm_result.get("error"):
        error_msg = llm_result['error']
        if "timeout" in error_msg.lower():
            raise HTTPException(
                status_code=504,
                detail=f"Code generation timed out after {llm_result.get('duration_ms', 0) / 1000:.0f}s. Try a simpler brief or reduce n_context.",
            )
        raise HTTPException(
            status_code=500,
            detail=f"LLM generation failed: {error_msg}",
        )

    duration_ms = int((time.monotonic() - start) * 1000)

    # Strip markdown code fences if the LLM wrapped the output
    code = llm_result["content"]
    code = _strip_code_fences(code)

    # Build updated history for the client to store and send back next turn
    updated_history = list(req.history) + [
        HistoryMessage(role="user", content=req.brief),
        HistoryMessage(role="assistant", content=code),
    ]

    return GenerateResponse(
        code=code,
        context_used=context_chunks,
        model=llm_result["model"],
        duration_ms=duration_ms,
        task=req.task,
        history=updated_history,
    )


@app.get("/templates/{category}", response_model=TemplatesResponse)
async def list_templates(category: str):
    """List available templates from the design library by component category."""
    embedder: EmbeddingClient = app.state.embedder
    store: VectorStore = app.state.store

    if category not in VALID_CATEGORIES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid category '{category}'. Valid: {sorted(VALID_CATEGORIES)}",
        )

    # Embed the category name to find relevant templates
    embed_result = embedder.embed(f"{category} section component")
    if embed_result is None:
        raise HTTPException(status_code=502, detail="Failed to embed category query")

    results = store.search(
        query_embedding=embed_result.embedding,
        n_results=20,
        component_category=category,
        exclude_sections=["head-meta"],
    )

    # Deduplicate by file path (keep best chunk per file)
    seen_files = {}
    for r in results:
        if r.file_path not in seen_files:
            seen_files[r.file_path] = r

    templates = [
        TemplateItem(
            file_path=r.file_path,
            framework=r.framework,
            repo_name=r.repo_name or "",
            preview=r.text[:200].strip(),
            text=r.text,
        )
        for r in seen_files.values()
    ]

    return TemplatesResponse(
        category=category,
        count=len(templates),
        templates=templates,
    )


@app.post("/seo/audit")
async def seo_audit(req: SEOAuditRequest):
    """Run an SEO audit on HTML content."""
    if not req.html.strip():
        raise HTTPException(status_code=400, detail="HTML content cannot be empty")

    return audit_html(req.html)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _strip_code_fences(text: str) -> str:
    """Remove markdown code fences if the LLM wrapped its output."""
    text = text.strip()
    # Remove ```html ... ``` or ```css ... ``` etc.
    if text.startswith("```"):
        # Find end of first line (e.g., ```html)
        first_newline = text.find("\n")
        if first_newline != -1:
            text = text[first_newline + 1:]
        # Remove trailing ```
        if text.endswith("```"):
            text = text[:-3].rstrip()
    return text
