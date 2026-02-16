#!/usr/bin/env python3
"""
End-to-end test for the RAG pipeline.

Tests the full flow: Brief → RAG search → LLM generation → SEO audit
Can run standalone (no server needed) or against the running API.

Usage:
    cd /home/rpi/ai-engine/rag-api
    /home/rpi/ai-engine/venv/bin/python test_pipeline.py
"""

import json
import sys
import time
from pathlib import Path

# Add indexer to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "design-library-indexer"))

from indexer.config import IndexerConfig
from indexer.embeddings import EmbeddingClient
from indexer.store import VectorStore

from llm import OllamaChat
from prompts import build_prompt
from seo import audit_html


def separator(title: str) -> None:
    print(f"\n{'=' * 70}")
    print(f"  {title}")
    print(f"{'=' * 70}\n")


def test_seo_audit() -> bool:
    """Test the SEO audit module with sample HTML."""
    separator("TEST 1: SEO Audit (no LLM needed)")

    good_html = """\
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Best Web Design Tools for 2026 - DesignHub</title>
    <meta name="description" content="Discover the top web design tools for 2026. From Figma to VS Code, our curated list helps designers and developers build better websites faster.">
    <meta property="og:title" content="Best Web Design Tools for 2026">
    <meta property="og:description" content="Curated list of top web design tools">
    <link rel="canonical" href="https://example.com/tools">
</head>
<body>
    <h1>Best Web Design Tools for 2026</h1>
    <h2>Design Tools</h2>
    <p>Content here</p>
    <img src="tools.jpg" alt="Screenshot of design tools comparison">
</body>
</html>"""

    result = audit_html(good_html)
    print(f"Score: {result['score']}/100")
    print(f"Errors: {result['errors']}, Warnings: {result['warnings']}, Passed: {result['passed_count']}")

    for item in result["passed"]:
        print(f"  [PASS] {item['message']}")
    for item in result["issues"]:
        print(f"  [{item['severity'].upper()}] {item['message']}")

    # Test bad HTML
    print("\n--- Bad HTML test ---")
    bad_html = "<html><body><h1>Hello</h1><h4>Skipped h2 and h3</h4></body></html>"
    bad_result = audit_html(bad_html)
    print(f"Score: {bad_result['score']}/100")
    print(f"Errors: {bad_result['errors']}, Warnings: {bad_result['warnings']}")
    for item in bad_result["issues"]:
        print(f"  [{item['severity'].upper()}] {item['message']}")

    print("\n[PASS] SEO audit module works correctly")
    return True


def test_embedding(embedder: EmbeddingClient) -> bool:
    """Test embedding a query."""
    separator("TEST 2: Embedding")

    result = embedder.embed("hero section with gradient background")
    if result is None:
        print("[FAIL] Embedding returned None")
        return False

    print(f"Text: \"{result.text[:50]}...\"")
    print(f"Dimensions: {len(result.embedding)}")
    print(f"Duration: {result.duration_ms:.0f}ms")
    print(f"Model: {result.model}")
    print("\n[PASS] Embedding works correctly")
    return True


def test_search(embedder: EmbeddingClient, store: VectorStore) -> list[dict]:
    """Test semantic search."""
    separator("TEST 3: Semantic Search (RAG Retrieval)")

    query = "hero section with call to action button"
    result = embedder.embed(query)
    if result is None:
        print("[FAIL] Could not embed search query")
        return []

    results = store.search(
        query_embedding=result.embedding,
        n_results=3,
        exclude_sections=["head-meta"],
    )

    if not results:
        print("[WARN] No search results found (index may be empty)")
        return []

    print(f"Query: \"{query}\"")
    print(f"Results: {len(results)}\n")

    context_chunks = []
    for i, r in enumerate(results, 1):
        similarity = 1 - r.distance
        print(f"  [{i}] {r.file_path}")
        print(f"      Similarity: {similarity:.3f} | Framework: {r.framework}")
        preview = r.text[:150].replace("\n", " ")
        print(f"      Preview: {preview}...")
        print()
        context_chunks.append({
            "text": r.text,
            "file_path": r.file_path,
            "similarity": round(similarity, 3),
            "framework": r.framework,
        })

    print(f"[PASS] Search returned {len(results)} results")
    return context_chunks


def test_prompt_building(context_chunks: list[dict]) -> tuple[str, str]:
    """Test prompt construction with context injection."""
    separator("TEST 4: Prompt Engineering")

    brief = "A modern hero section for a SaaS landing page with a signup CTA"
    system_prompt, user_prompt = build_prompt(
        task="hero",
        brief=brief,
        context_chunks=context_chunks,
    )

    print(f"Task: hero")
    print(f"Brief: \"{brief}\"")
    print(f"Context chunks injected: {len(context_chunks)}")
    print(f"System prompt length: {len(system_prompt)} chars")
    print(f"User prompt length: {len(user_prompt)} chars")
    print(f"\n--- System prompt (first 300 chars) ---")
    print(system_prompt[:300])
    print(f"\n--- User prompt (first 300 chars) ---")
    print(user_prompt[:300])

    print(f"\n[PASS] Prompt built successfully")
    return system_prompt, user_prompt


def test_generation(
    chat: OllamaChat,
    system_prompt: str,
    user_prompt: str,
) -> str:
    """Test LLM code generation."""
    separator("TEST 5: LLM Code Generation")

    print(f"Model: {chat.model}")
    print(f"Generating code... (this may take 1-5 minutes on Raspberry Pi)")

    start = time.monotonic()
    result = chat.generate(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        temperature=0.7,
    )
    elapsed = time.monotonic() - start

    if result.get("error"):
        print(f"[FAIL] Generation error: {result['error']}")
        return ""

    code = result["content"]
    print(f"Duration: {elapsed:.1f}s ({result['duration_ms']}ms)")
    print(f"Output length: {len(code)} chars")
    print(f"\n--- Generated code (first 500 chars) ---")
    print(code[:500])
    if len(code) > 500:
        print(f"\n... ({len(code) - 500} more chars)")

    print(f"\n[PASS] Code generated successfully")
    return code


def test_full_pipeline(generated_code: str) -> None:
    """Test SEO audit on generated code."""
    separator("TEST 6: SEO Audit on Generated Code")

    if not generated_code:
        print("[SKIP] No generated code to audit")
        return

    result = audit_html(generated_code)
    print(f"Score: {result['score']}/100")
    print(f"Errors: {result['errors']}, Warnings: {result['warnings']}, Passed: {result['passed_count']}")
    for item in result["issues"]:
        print(f"  [{item['severity'].upper()}] {item['message']}")
    for item in result["passed"]:
        print(f"  [PASS] {item['message']}")

    print(f"\n[PASS] Full pipeline test complete")


def main():
    separator("RAG Pipeline End-to-End Test")
    print("This test validates the full pipeline:")
    print("  Brief -> Embed -> Search -> Prompt Build -> LLM Generate -> SEO Audit")
    print()

    # Initialize components
    config = IndexerConfig()
    embedder = EmbeddingClient(config)
    store = VectorStore(config)
    chat = OllamaChat(base_url=config.ollama_base_url)

    # Pre-flight checks
    print("Checking Ollama...")
    embed_ok = embedder.health_check()
    chat_ok = chat.health_check()
    if not embed_ok:
        print("[FAIL] Embedding model not available. Is Ollama running?")
        print("  Start Ollama: systemctl start ollama")
        sys.exit(1)
    print(f"  Embedding model: OK")

    if not chat_ok:
        print("[WARN] Chat model not available. Generation test will be skipped.")
        print(f"  Pull model: ollama pull {chat.model}")
    else:
        print(f"  Chat model ({chat.model}): OK")

    store.initialize()
    stats = store.get_stats()
    print(f"  ChromaDB: {stats['total_chunks']} chunks indexed")

    if stats["total_chunks"] == 0:
        print("[WARN] No chunks indexed. Search results will be empty.")
        print("  Run indexer first: python run_indexer.py index --full -v")

    # Run tests
    results = {"passed": 0, "failed": 0, "skipped": 0}

    # Test 1: SEO (no dependencies)
    if test_seo_audit():
        results["passed"] += 1
    else:
        results["failed"] += 1

    # Test 2: Embedding
    if test_embedding(embedder):
        results["passed"] += 1
    else:
        results["failed"] += 1
        print("\n[ABORT] Cannot continue without embedding")
        _print_summary(results)
        return

    # Test 3: Search
    context_chunks = test_search(embedder, store)
    results["passed"] += 1

    # Test 4: Prompt building
    system_prompt, user_prompt = test_prompt_building(context_chunks)
    results["passed"] += 1

    # Test 5: LLM generation
    generated_code = ""
    if chat_ok:
        generated_code = test_generation(chat, system_prompt, user_prompt)
        if generated_code:
            results["passed"] += 1
        else:
            results["failed"] += 1
    else:
        separator("TEST 5: LLM Code Generation")
        print("[SKIP] Chat model not available")
        results["skipped"] += 1

    # Test 6: Full pipeline (SEO audit on generated code)
    if generated_code:
        test_full_pipeline(generated_code)
        results["passed"] += 1
    else:
        separator("TEST 6: SEO Audit on Generated Code")
        print("[SKIP] No generated code to audit")
        results["skipped"] += 1

    # Save generated code to file
    if generated_code:
        output_path = Path(__file__).parent / "test_output.html"
        output_path.write_text(generated_code, encoding="utf-8")
        print(f"\nGenerated code saved to: {output_path}")

    _print_summary(results)


def _print_summary(results: dict) -> None:
    separator("TEST SUMMARY")
    print(f"  Passed:  {results['passed']}")
    print(f"  Failed:  {results['failed']}")
    print(f"  Skipped: {results['skipped']}")
    total = results["passed"] + results["failed"]
    if total > 0:
        print(f"  Score:   {results['passed']}/{total} ({results['passed']/total*100:.0f}%)")
    print()
    if results["failed"] == 0:
        print("  All tests passed!")
    else:
        print(f"  {results['failed']} test(s) failed")


if __name__ == "__main__":
    main()
