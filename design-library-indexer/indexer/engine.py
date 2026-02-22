"""
Indexer engine — orchestrates the full indexing pipeline.

Pipeline: discover files → chunk → embed → store in ChromaDB

Supports:
- Full re-index (processes everything)
- Incremental index (only changed files, via SHA256 hashing)
- Cleanup of deleted files from the vector store
"""

import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from .autotune import choose_worker_count, get_cpu_temp
from .chunker import Chunker
from .config import IndexerConfig
from .discovery import FileDiscovery, DiscoveredFile
from .embeddings import EmbeddingClient
from .store import VectorStore

logger = logging.getLogger(__name__)


class IndexerEngine:
    """Main indexing pipeline orchestrator."""

    def __init__(self, config: IndexerConfig | None = None):
        self.config = config or IndexerConfig()
        self.discovery = FileDiscovery(self.config)
        self.chunker = Chunker(self.config)
        self.embedder = EmbeddingClient(self.config)
        self.store = VectorStore(self.config)

        # Stats tracking
        self._stats = {
            "run_start": None,
            "run_end": None,
            "files_processed": 0,
            "files_skipped_read_error": 0,
            "chunks_created": 0,
            "chunks_embedded": 0,
            "chunks_stored": 0,
            "embedding_failures": 0,
            "files_deleted_from_store": 0,
            "total_embedding_time_ms": 0.0,
        }

    def run(self, full: bool = False) -> dict:
        """
        Execute the indexing pipeline.

        Args:
            full: If True, re-index everything. If False, incremental only.

        Returns:
            Stats dict with indexing results.
        """
        self._stats["run_start"] = datetime.now(timezone.utc).isoformat()
        incremental = not full
        mode = "FULL" if full else "INCREMENTAL"

        logger.info(f"═══ Starting {mode} index run ═══")

        # ── Pre-flight checks ──
        if not self.config.library_root.exists():
            logger.error(f"Library root does not exist: {self.config.library_root}")
            return self._stats

        if not self.embedder.health_check():
            logger.error("Ollama health check failed. Aborting.")
            return self._stats

        self.store.initialize()

        if full:
            logger.warning("Full re-index: resetting vector store")
            self.store.reset()
            self.store.initialize()

        # ── Count files for progress tracking ──
        logger.info("Scanning library to count indexable files...")
        total_files = self.discovery.count_indexable_files(incremental=incremental)
        logger.info(f"Found {total_files} files to index")
        self._stats["total_files"] = total_files

        # ── Process files ──
        batch_ids: list[str] = []
        batch_embeddings: list[list[float]] = []
        batch_documents: list[str] = []
        batch_metadatas: list[dict] = []
        progress_start = time.monotonic()

        # Choose worker count once at startup; re-check every 50 files for thermal protection
        workers = choose_worker_count(max_workers=3, min_workers=1, default_workers=3)
        autotune_interval = 50
        throttled = False  # True when held at 2 workers due to high temp

        for discovered_file in self.discovery.discover(incremental=incremental):
            self._process_file(
                discovered_file,
                batch_ids, batch_embeddings, batch_documents, batch_metadatas,
                workers=workers,
            )

            # Log progress
            processed = self._stats["files_processed"]
            if total_files > 0 and processed % self.config.log_every_n_files == 0:
                self._log_progress(processed, total_files, progress_start)

            # Re-evaluate workers periodically for thermal protection (not every file)
            if processed > 0 and processed % autotune_interval == 0:
                temp = get_cpu_temp()
                if temp is not None:
                    if temp > 75:
                        # Throttle: hold at 2 workers until temp recovers
                        workers = 2
                        if not throttled:
                            throttled = True
                            logger.warning(f"Thermal throttle: {temp:.0f}°C > 75°C — workers capped at 2")
                    elif throttled and temp < 65:
                        # Recovery: temp dropped below 65°C, restore full workers
                        throttled = False
                        workers = choose_worker_count(max_workers=3, min_workers=1, default_workers=3)
                        logger.info(f"Thermal recovery: {temp:.0f}°C < 65°C — workers restored to {workers}")
                    elif not throttled:
                        workers = choose_worker_count(max_workers=3, min_workers=1, default_workers=3)
                else:
                    if not throttled:
                        workers = choose_worker_count(max_workers=3, min_workers=1, default_workers=3)

            # Flush batch when it hits the configured size
            if len(batch_ids) >= self.config.batch_size:
                self._flush_batch(batch_ids, batch_embeddings, batch_documents, batch_metadatas)
                batch_ids.clear()
                batch_embeddings.clear()
                batch_documents.clear()
                batch_metadatas.clear()

        # Flush remaining
        if batch_ids:
            self._flush_batch(batch_ids, batch_embeddings, batch_documents, batch_metadatas)

        # ── Cleanup deleted files ──
        if incremental:
            deleted = self.discovery.get_deleted_files()
            if deleted:
                logger.info(f"Cleaning up {len(deleted)} deleted files from vector store")
                for rel_path in deleted:
                    self.store.delete_by_file(rel_path)
                    self._stats["files_deleted_from_store"] += 1

        # ── Save state ──
        self.discovery.save_current_hashes()
        self._stats["run_end"] = datetime.now(timezone.utc).isoformat()
        self._save_stats()
        self._save_log()

        logger.info(f"═══ Index run complete ═══")
        self._log_summary()

        return self._stats

    def _process_file(
        self,
        discovered: DiscoveredFile,
        batch_ids: list[str],
        batch_embeddings: list[list[float]],
        batch_documents: list[str],
        batch_metadatas: list[dict],
        workers: int = 3,
    ) -> None:
        """Process a single file: read → chunk → embed → add to batch."""

        # ── Read file content ──
        try:
            content = discovered.path.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            logger.warning(f"Cannot read file {discovered.path}: {e}")
            self._stats["files_skipped_read_error"] += 1
            return

        if not content.strip():
            return

        self._stats["files_processed"] += 1

        # ── Delete old chunks for this file (incremental update) ──
        self.store.delete_by_file(discovered.relative_path)

        # ── Chunk the file ──
        if discovered.file_type == "config":
            # Config files are stored as a single chunk with metadata
            chunks_data = [{
                "text": content,
                "section_type": "config",
                "chunk_index": 0,
            }]
        else:
            raw_chunks = self.chunker.chunk(content, discovered.extension)
            chunks_data = [
                {
                    "text": c.text,
                    "section_type": c.section_type,
                    "chunk_index": c.chunk_index,
                }
                for c in raw_chunks
            ]

        if not chunks_data:
            return

        self._stats["chunks_created"] += len(chunks_data)

        # ── Embed chunks in parallel ──
        # Prepare embedding tasks
        embed_tasks = []
        for chunk_data in chunks_data:
            embed_prefix = self._build_embed_prefix(discovered, chunk_data["section_type"])
            embed_text = f"{embed_prefix}\n\n{chunk_data['text']}"
            embed_tasks.append((chunk_data, embed_text))

        # Parallel embedding with ThreadPoolExecutor.
        # EmbeddingClient._ollama_lock ensures only one HTTP request reaches
        # Ollama at a time, so workers prepare text in parallel without
        # stacking up connections that cause timeout warnings.
        with ThreadPoolExecutor(max_workers=workers) as executor:
            # Submit all embedding tasks
            futures = {
                executor.submit(self.embedder.embed, embed_text): (chunk_data, embed_text)
                for chunk_data, embed_text in embed_tasks
            }

            # Collect results as they complete
            for future in as_completed(futures):
                chunk_data, embed_text = futures[future]

                try:
                    result = future.result()

                    if result is None:
                        self._stats["embedding_failures"] += 1
                        continue

                    self._stats["chunks_embedded"] += 1
                    self._stats["total_embedding_time_ms"] += result.duration_ms

                    chunk_id = f"{discovered.relative_path}::{chunk_data['chunk_index']}"

                    batch_ids.append(chunk_id)
                    batch_embeddings.append(result.embedding)
                    batch_documents.append(chunk_data["text"])
                    batch_metadatas.append({
                        "file_path": discovered.relative_path,
                        "extension": discovered.extension,
                        "framework": discovered.framework,
                        "repo_name": discovered.repo_name,
                        "component_category": discovered.component_category,
                        "section_type": chunk_data["section_type"],
                        "file_type": discovered.file_type,
                        "chunk_index": chunk_data["chunk_index"],
                        "file_size": discovered.size_bytes,
                        "sha256": discovered.sha256,
                    })

                except Exception as e:
                    logger.warning(f"Embedding task failed: {e}")
                    self._stats["embedding_failures"] += 1

    def _build_embed_prefix(self, discovered: DiscoveredFile, section_type: str) -> str:
        """
        Build a contextual prefix for the embedding.

        This significantly improves retrieval quality. Instead of embedding
        raw code in isolation, we prepend metadata that tells the embedding
        model WHAT this code is.

        Example prefix:
          "React component from shadcn-taxonomy repository.
           Hero section. Framework: nextjs. File: src/components/hero.tsx"
        """
        parts = []

        # Framework context
        framework_labels = {
            "html": "HTML/CSS webpage",
            "react": "React component",
            "nextjs": "Next.js component",
            "astro": "Astro component",
            "vue": "Vue.js component",
            "svelte": "Svelte component",
            "css": "CSS stylesheet",
            "typescript": "TypeScript module",
            "javascript": "JavaScript module",
            "config": "Configuration file",
        }
        parts.append(framework_labels.get(discovered.framework, "Web code"))

        # Repo context
        if discovered.repo_name:
            parts.append(f"from {discovered.repo_name} repository")

        # Component category
        if discovered.component_category:
            parts.append(f"{discovered.component_category} section")

        # Section type
        if section_type and section_type not in ("fragment", "rules"):
            parts.append(f"Section type: {section_type}")

        # File path (last part)
        parts.append(f"File: {discovered.relative_path}")

        return ". ".join(parts) + "."

    def _flush_batch(
        self,
        ids: list[str],
        embeddings: list[list[float]],
        documents: list[str],
        metadatas: list[dict],
    ) -> None:
        """Flush accumulated batch to ChromaDB."""
        try:
            self.store.upsert_batch(ids, embeddings, documents, metadatas)
            self._stats["chunks_stored"] += len(ids)
            logger.debug(f"Flushed batch of {len(ids)} chunks to ChromaDB")
        except Exception as e:
            logger.error(f"Batch flush failed: {e}")

    def _save_stats(self) -> None:
        """Save run statistics to disk."""
        stats_file = self.config.index_metadata_dir / "stats.json"
        self.config.index_metadata_dir.mkdir(parents=True, exist_ok=True)

        # Merge with vector store stats
        store_stats = self.store.get_stats()
        combined = {**self._stats, "store": store_stats}

        with open(stats_file, "w") as f:
            json.dump(combined, f, indent=2)

    def _save_log(self) -> None:
        """Append run log as JSONL."""
        log_file = self.config.index_metadata_dir / "index_log.jsonl"
        self.config.index_metadata_dir.mkdir(parents=True, exist_ok=True)

        with open(log_file, "a") as f:
            f.write(json.dumps(self._stats) + "\n")

    def _log_progress(self, processed: int, total: int, start_time: float) -> None:
        """Log indexing progress with percentage, counts, and ETA."""
        pct = (processed / total) * 100
        remaining = total - processed
        elapsed = time.monotonic() - start_time

        if processed > 0 and elapsed > 0:
            rate = processed / elapsed  # files per second
            eta_seconds = remaining / rate
            # Format ETA as human-readable
            if eta_seconds < 60:
                eta_str = f"{eta_seconds:.0f}s"
            elif eta_seconds < 3600:
                eta_str = f"{eta_seconds / 60:.0f}m {eta_seconds % 60:.0f}s"
            else:
                hours = int(eta_seconds // 3600)
                mins = int((eta_seconds % 3600) // 60)
                eta_str = f"{hours}h {mins}m"
        else:
            eta_str = "calculating..."

        logger.info(
            f"Progress: {processed}/{total} files ({pct:.1f}%) │ "
            f"{remaining} remaining │ ETA: {eta_str}"
        )

    def _log_summary(self) -> None:
        """Log a human-readable summary of the indexing run."""
        s = self._stats
        avg_embed_ms = (
            s["total_embedding_time_ms"] / s["chunks_embedded"]
            if s["chunks_embedded"] > 0 else 0
        )
        logger.info(
            f"\n"
            f"  ┌─── Indexing Summary ────────────────────────┐\n"
            f"  │ Files processed:       {s['files_processed']:>8}            │\n"
            f"  │ Files read errors:     {s['files_skipped_read_error']:>8}            │\n"
            f"  │ Chunks created:        {s['chunks_created']:>8}            │\n"
            f"  │ Chunks embedded:       {s['chunks_embedded']:>8}            │\n"
            f"  │ Chunks stored:         {s['chunks_stored']:>8}            │\n"
            f"  │ Embedding failures:    {s['embedding_failures']:>8}            │\n"
            f"  │ Deleted file cleanup:  {s['files_deleted_from_store']:>8}            │\n"
            f"  │ Avg embed time:        {avg_embed_ms:>8.1f} ms         │\n"
            f"  │ Start: {s['run_start']}       │\n"
            f"  │ End:   {s['run_end']}       │\n"
            f"  └─────────────────────────────────────────────┘"
        )
