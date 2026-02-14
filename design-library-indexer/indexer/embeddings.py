"""
Embedding client — interfaces with Ollama for vector embeddings.

Uses nomic-embed-text by default (768-dimensional embeddings).
Handles batching, retries, and connection errors gracefully.
"""

import logging
import time
from dataclasses import dataclass

import requests

from .config import IndexerConfig

logger = logging.getLogger(__name__)


@dataclass
class EmbeddingResult:
    """Result of an embedding request."""
    text: str
    embedding: list[float]
    model: str
    duration_ms: float


class EmbeddingClient:
    """Client for Ollama embedding API."""

    def __init__(self, config: IndexerConfig):
        self.config = config
        self.base_url = config.ollama_base_url
        self.model = config.embedding_model
        self._session = requests.Session()
        self._session.headers.update({"Content-Type": "application/json"})

    def health_check(self) -> bool:
        """Verify Ollama is running and the embedding model is available."""
        try:
            # Check Ollama is up
            resp = self._session.get(f"{self.base_url}/api/tags", timeout=5)
            resp.raise_for_status()
            models = resp.json().get("models", [])
            model_names = [m.get("name", "") for m in models]

            # Check our model is pulled
            # Ollama returns names like "nomic-embed-text:latest"
            found = any(self.model in name for name in model_names)
            if not found:
                logger.error(
                    f"Embedding model '{self.model}' not found. "
                    f"Available models: {model_names}. "
                    f"Run: ollama pull {self.model}"
                )
                return False

            logger.info(f"Ollama healthy. Embedding model '{self.model}' available.")
            return True

        except requests.ConnectionError:
            logger.error(
                f"Cannot connect to Ollama at {self.base_url}. "
                f"Is Ollama running? Start it with: ollama serve"
            )
            return False
        except Exception as e:
            logger.error(f"Ollama health check failed: {e}")
            return False

    def embed(self, text: str, max_retries: int = 3) -> EmbeddingResult | None:
        """
        Generate embedding for a single text.

        Args:
            text: The text to embed.
            max_retries: Number of retries on transient failures.

        Returns:
            EmbeddingResult or None on failure.
        """
        # Truncate very long texts — nomic-embed-text has 8192 token limit
        # ~4 chars per token, leave some margin
        max_chars = 30_000
        if len(text) > max_chars:
            text = text[:max_chars]
            logger.debug(f"Truncated text to {max_chars} chars for embedding")

        for attempt in range(max_retries):
            try:
                start = time.monotonic()
                resp = self._session.post(
                    f"{self.base_url}/api/embed",
                    json={
                        "model": self.model,
                        "input": text,
                    },
                    timeout=600,  # 10 minutes for Raspberry Pi hardware
                )
                resp.raise_for_status()
                duration_ms = (time.monotonic() - start) * 1000

                data = resp.json()
                embeddings = data.get("embeddings", [])
                if not embeddings or not embeddings[0]:
                    logger.warning(f"Empty embedding returned for text ({len(text)} chars)")
                    return None

                return EmbeddingResult(
                    text=text,
                    embedding=embeddings[0],
                    model=self.model,
                    duration_ms=duration_ms,
                )

            except requests.ConnectionError:
                logger.warning(f"Connection to Ollama lost (attempt {attempt + 1}/{max_retries})")
                time.sleep(2 ** attempt)  # Exponential backoff
            except requests.Timeout:
                logger.warning(f"Embedding request timed out (attempt {attempt + 1}/{max_retries})")
                time.sleep(2 ** attempt)
            except requests.HTTPError as e:
                logger.error(f"Ollama API error: {e}")
                if resp.status_code >= 500:
                    time.sleep(2 ** attempt)
                    continue
                return None
            except Exception as e:
                logger.error(f"Unexpected embedding error: {e}")
                return None

        logger.error(f"Failed to embed text after {max_retries} retries")
        return None

    def embed_batch(self, texts: list[str]) -> list[EmbeddingResult | None]:
        """
        Embed multiple texts sequentially.

        Ollama doesn't support true batch embedding via API,
        so we call embed() in a loop. On Pi hardware, this is
        fine — the bottleneck is the model, not the HTTP overhead.
        """
        results = []
        for i, text in enumerate(texts):
            result = self.embed(text)
            results.append(result)
            if (i + 1) % 10 == 0:
                logger.debug(f"Embedded {i + 1}/{len(texts)} chunks")
        return results
