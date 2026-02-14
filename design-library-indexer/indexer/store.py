"""
Vector store — ChromaDB interface for storing and querying design file embeddings.

Provides upsert, delete, and semantic search over the indexed design library.
Uses persistent storage on disk (SQLite + Parquet via ChromaDB).
"""

import logging
from dataclasses import dataclass

import chromadb
from chromadb.config import Settings

from .config import IndexerConfig

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    """A single search result from the vector store."""
    chunk_id: str
    file_path: str
    text: str
    distance: float          # lower = more similar
    framework: str
    component_category: str
    section_type: str
    repo_name: str


class VectorStore:
    """ChromaDB-backed vector store for the design library."""

    def __init__(self, config: IndexerConfig):
        self.config = config
        self._client: chromadb.ClientAPI | None = None
        self._collection: chromadb.Collection | None = None

    def initialize(self) -> None:
        """Initialize ChromaDB client and collection."""
        self.config.chroma_persist_dir.mkdir(parents=True, exist_ok=True)

        self._client = chromadb.PersistentClient(
            path=str(self.config.chroma_persist_dir),
            settings=Settings(
                anonymized_telemetry=False,
                allow_reset=True,
            ),
        )

        self._collection = self._client.get_or_create_collection(
            name=self.config.chroma_collection_name,
            metadata={
                "hnsw:space": "cosine",  # cosine similarity for nomic-embed-text
                "description": "Design library code chunks with embeddings",
            },
        )

        count = self._collection.count()
        logger.info(
            f"ChromaDB initialized. Collection '{self.config.chroma_collection_name}' "
            f"has {count} existing documents."
        )

    def upsert_batch(
        self,
        ids: list[str],
        embeddings: list[list[float]],
        documents: list[str],
        metadatas: list[dict],
    ) -> None:
        """
        Upsert a batch of chunks into ChromaDB.

        Args:
            ids: Unique IDs for each chunk (format: "{relative_path}::{chunk_index}")
            embeddings: Embedding vectors
            documents: Raw text of each chunk
            metadatas: Metadata dicts for each chunk
        """
        if not ids:
            return

        try:
            self._collection.upsert(
                ids=ids,
                embeddings=embeddings,
                documents=documents,
                metadatas=metadatas,
            )
            logger.debug(f"Upserted {len(ids)} chunks to ChromaDB")
        except Exception as e:
            logger.error(f"ChromaDB upsert failed: {e}")
            raise

    def delete_by_file(self, relative_path: str) -> None:
        """
        Delete all chunks belonging to a specific file.

        Uses metadata filter since chunk IDs are prefixed with the file path.
        """
        try:
            self._collection.delete(
                where={"file_path": relative_path}
            )
            logger.debug(f"Deleted chunks for file: {relative_path}")
        except Exception as e:
            logger.warning(f"Failed to delete chunks for {relative_path}: {e}")

    def delete_by_prefix(self, id_prefix: str) -> None:
        """Delete all chunks whose ID starts with the given prefix."""
        try:
            # ChromaDB doesn't support prefix deletion natively.
            # We need to query for matching IDs first.
            results = self._collection.get(
                where={"file_path": id_prefix},
            )
            if results["ids"]:
                self._collection.delete(ids=results["ids"])
                logger.debug(f"Deleted {len(results['ids'])} chunks with prefix: {id_prefix}")
        except Exception as e:
            logger.warning(f"Failed to delete by prefix {id_prefix}: {e}")

    def search(
        self,
        query_embedding: list[float],
        n_results: int = 10,
        framework: str | None = None,
        component_category: str | None = None,
        section_type: str | None = None,
    ) -> list[SearchResult]:
        """
        Semantic search over the design library.

        Args:
            query_embedding: The embedding vector of the search query.
            n_results: Number of results to return.
            framework: Optional filter (e.g., "react", "html", "astro").
            component_category: Optional filter (e.g., "hero", "header", "footer").
            section_type: Optional filter (e.g., "component", "style", "head").

        Returns:
            List of SearchResult objects sorted by relevance.
        """
        where_filter = self._build_where_filter(framework, component_category, section_type)

        try:
            results = self._collection.query(
                query_embeddings=[query_embedding],
                n_results=n_results,
                where=where_filter if where_filter else None,
                include=["documents", "metadatas", "distances"],
            )
        except Exception as e:
            logger.error(f"ChromaDB query failed: {e}")
            return []

        search_results = []
        if results["ids"] and results["ids"][0]:
            for i, chunk_id in enumerate(results["ids"][0]):
                metadata = results["metadatas"][0][i] if results["metadatas"] else {}
                search_results.append(SearchResult(
                    chunk_id=chunk_id,
                    file_path=metadata.get("file_path", ""),
                    text=results["documents"][0][i] if results["documents"] else "",
                    distance=results["distances"][0][i] if results["distances"] else 1.0,
                    framework=metadata.get("framework", ""),
                    component_category=metadata.get("component_category", ""),
                    section_type=metadata.get("section_type", ""),
                    repo_name=metadata.get("repo_name", ""),
                ))

        return search_results

    def get_stats(self) -> dict:
        """Return collection statistics."""
        count = self._collection.count()

        # Sample metadata to get framework distribution
        framework_counts: dict[str, int] = {}
        category_counts: dict[str, int] = {}

        if count > 0:
            # Peek at up to 1000 docs for stats
            sample_size = min(count, 1000)
            sample = self._collection.peek(limit=sample_size)
            if sample["metadatas"]:
                for meta in sample["metadatas"]:
                    fw = meta.get("framework", "unknown")
                    framework_counts[fw] = framework_counts.get(fw, 0) + 1
                    cat = meta.get("component_category", "")
                    if cat:
                        category_counts[cat] = category_counts.get(cat, 0) + 1

        return {
            "total_chunks": count,
            "framework_distribution": framework_counts,
            "component_categories": category_counts,
        }

    def reset(self) -> None:
        """Delete all data and recreate the collection. Use with caution."""
        logger.warning("Resetting ChromaDB collection — all data will be deleted")
        self._client.delete_collection(self.config.chroma_collection_name)
        self._collection = self._client.create_collection(
            name=self.config.chroma_collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info("Collection reset complete")

    # ── Private ────────────────────────────────────────────────────────

    def _build_where_filter(
        self,
        framework: str | None,
        component_category: str | None,
        section_type: str | None,
    ) -> dict | None:
        """Build a ChromaDB where filter from optional parameters."""
        conditions = []
        if framework:
            conditions.append({"framework": framework})
        if component_category:
            conditions.append({"component_category": component_category})
        if section_type:
            conditions.append({"section_type": section_type})

        if not conditions:
            return None
        if len(conditions) == 1:
            return conditions[0]
        return {"$and": conditions}
