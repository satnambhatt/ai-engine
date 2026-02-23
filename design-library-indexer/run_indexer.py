#!/usr/bin/env python3
"""
Design Library Indexer — CLI entry point.

Usage:
    # Incremental index (only changed files):
    python run_indexer.py

    # Full re-index (wipes vector store and re-processes everything):
    python run_indexer.py --full

    # Custom library path:
    python run_indexer.py --library-root /path/to/design-library

    # Stats only (no indexing):
    python run_indexer.py --stats

    # Search test:
    python run_indexer.py --search "hero section with gradient background"

    # Search with filters:
    python run_indexer.py --search "responsive nav" --framework react --category header
"""

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from logging.handlers import RotatingFileHandler

from indexer.config import IndexerConfig
from indexer.embeddings import EmbeddingClient
from indexer.engine import IndexerEngine
from indexer.store import VectorStore


def setup_logging(verbose: bool = False) -> None:
    """Configure logging output to both console and file."""
    level = logging.DEBUG if verbose else logging.INFO

    # Create logs directory if it doesn't exist
    log_dir = Path.home() / "ai-engine" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(
        logging.Formatter(
            "%(asctime)s │ %(levelname)-7s │ %(name)s │ %(message)s",
            datefmt="%H:%M:%S"
        )
    )

    # File handler with rotation (5MB per file, keep 10 backup files)
    file_handler = RotatingFileHandler(
        log_dir / "indexer-manual.log",
        maxBytes=5_242_880,  # 5MB
        backupCount=10,
        encoding="utf-8"
    )
    file_handler.setFormatter(
        logging.Formatter(
            "%(asctime)s │ %(levelname)-7s │ %(name)s │ %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
    )

    # Configure root logger
    logging.basicConfig(
        level=level,
        handlers=[console_handler, file_handler],
    )

    # Quiet noisy libraries
    logging.getLogger("chromadb").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)


def cmd_index(args) -> None:
    """Run the indexing pipeline."""
    config = build_config(args)
    engine = IndexerEngine(config)
    stats = engine.run(full=args.full)

    if stats["files_processed"] == 0 and not args.full:
        print("\nNo changes detected. Library is up to date.")
        print("Use --full to force a complete re-index.")


def cmd_stats(args) -> None:
    """Show current index statistics."""
    config = build_config(args)
    store = VectorStore(config)
    store.initialize()

    stats = store.get_stats()
    print(json.dumps(stats, indent=2))

    # Also show file hash count
    hash_file = config.index_metadata_dir / "file_hashes.json"
    if hash_file.exists():
        with open(hash_file) as f:
            hashes = json.load(f)
        print(f"\nTracked files: {len(hashes)}")

    # Show last run log
    log_file = config.index_metadata_dir / "index_log.jsonl"
    if log_file.exists():
        with open(log_file) as f:
            lines = f.readlines()
        if lines:
            last_run = json.loads(lines[-1])
            print(f"\nLast run: {last_run.get('run_start', 'unknown')}")
            print(f"  Files processed: {last_run.get('files_processed', 0)}")
            print(f"  Chunks stored: {last_run.get('chunks_stored', 0)}")


def cmd_search(args) -> None:
    """Test semantic search against the index."""
    config = build_config(args)

    # Embed the query
    embedder = EmbeddingClient(config)
    if not embedder.health_check():
        print("ERROR: Ollama is not available.", file=sys.stderr)
        sys.exit(1)

    result = embedder.embed(args.search)
    if result is None:
        print("ERROR: Failed to embed search query.", file=sys.stderr)
        sys.exit(1)

    # Search
    store = VectorStore(config)
    store.initialize()

    exclude_sections = None if args.include_head else ["head-meta"]

    results = store.search(
        query_embedding=result.embedding,
        n_results=args.n_results,
        framework=args.framework,
        component_category=args.category,
        exclude_sections=exclude_sections,
    )

    if not results:
        print("No results found.")
        return

    print(f"\n{'─' * 80}")
    print(f"Search: \"{args.search}\"")
    if args.framework:
        print(f"Filter: framework={args.framework}")
    if args.category:
        print(f"Filter: category={args.category}")
    print(f"{'─' * 80}\n")

    for i, r in enumerate(results, 1):
        similarity = 1 - r.distance  # cosine distance → similarity
        print(f"  [{i}] {r.file_path}")
        print(f"      Similarity: {similarity:.3f} │ Framework: {r.framework} │ "
              f"Category: {r.component_category or 'n/a'} │ Section: {r.section_type}")
        print(f"      Repo: {r.repo_name or 'n/a'}")
        if args.show_code:
            print(f"      Code:\n{r.text.strip()}")
        else:
            # Show first 3 lines of the chunk
            preview = "\n".join(r.text.strip().split("\n")[:3])
            print(f"      Preview: {preview[:200]}...")
        print()


def cmd_reset(args) -> None:
    """Reset the vector store and file hashes. Destructive."""
    config = build_config(args)

    confirm = input("This will DELETE all indexed data. Type 'yes' to confirm: ")
    if confirm.strip().lower() != "yes":
        print("Aborted.")
        return

    store = VectorStore(config)
    store.initialize()
    store.reset()

    # Also clear file hashes
    hash_file = config.index_metadata_dir / "file_hashes.json"
    if hash_file.exists():
        hash_file.unlink()

    print("Vector store and file hashes have been reset.")


def build_config(args) -> IndexerConfig:
    """Build IndexerConfig from CLI arguments."""
    config = IndexerConfig()

    if hasattr(args, "library_root") and args.library_root:
        config.library_root = Path(args.library_root)
        config.index_metadata_dir = config.library_root / ".index"

    if hasattr(args, "chroma_dir") and args.chroma_dir:
        config.chroma_persist_dir = Path(args.chroma_dir)

    if hasattr(args, "ollama_url") and args.ollama_url:
        config.ollama_base_url = args.ollama_url

    return config


def _load_env_file() -> None:
    """Load ~/ai-engine/.env into os.environ (if it exists and not already set)."""
    env_path = Path.home() / "ai-engine" / ".env"
    if not env_path.exists():
        return
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip()
            if key and key not in os.environ:
                os.environ[key] = value


def main():
    _load_env_file()
    parser = argparse.ArgumentParser(
        description="Design Library Indexer — index web design files for AI-powered RAG",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # ── index command ──
    index_parser = subparsers.add_parser("index", help="Run the indexing pipeline")
    index_parser.add_argument("--full", action="store_true",
                              help="Full re-index (wipes and rebuilds)")
    index_parser.add_argument("-v", "--verbose", action="store_true")
    _add_common_args(index_parser)

    # ── stats command ──
    stats_parser = subparsers.add_parser("stats", help="Show index statistics")
    _add_common_args(stats_parser)

    # ── search command ──
    search_parser = subparsers.add_parser("search", help="Test semantic search")
    search_parser.add_argument("search", type=str, help="Search query text")
    search_parser.add_argument("-n", "--n-results", type=int, default=5)
    search_parser.add_argument("--framework", type=str, default=None,
                               help="Filter by framework (react, html, astro, etc.)")
    search_parser.add_argument("--category", type=str, default=None,
                               help="Filter by component category (hero, header, footer, etc.)")
    search_parser.add_argument("--show-code", action="store_true",
                               help="Show full chunk code instead of preview")
    search_parser.add_argument("--include-head", action="store_true",
                               help="Include <head> meta chunks in results (excluded by default)")
    _add_common_args(search_parser)

    # ── reset command ──
    reset_parser = subparsers.add_parser("reset", help="Reset all indexed data")
    _add_common_args(reset_parser)

    args = parser.parse_args()

    # Default to 'index' if no command given
    if args.command is None:
        args.command = "index"
        args.full = False
        args.verbose = False
        args.library_root = None
        args.chroma_dir = None
        args.ollama_url = None

    setup_logging(verbose=getattr(args, "verbose", False))

    commands = {
        "index": cmd_index,
        "stats": cmd_stats,
        "search": cmd_search,
        "reset": cmd_reset,
    }

    cmd_fn = commands.get(args.command)
    if cmd_fn:
        cmd_fn(args)
    else:
        parser.print_help()


def _add_common_args(parser):
    """Add arguments shared across all subcommands."""
    parser.add_argument("--library-root", type=str, default=None,
                        help="Path to design library (default: /mnt/design-library)")
    parser.add_argument("--chroma-dir", type=str, default=None,
                        help="Path to ChromaDB storage")
    parser.add_argument("--ollama-url", type=str, default=None,
                        help="Ollama API URL (default: http://localhost:11434)")


if __name__ == "__main__":
    main()
