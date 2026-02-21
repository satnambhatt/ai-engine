"""
Ollama Chat Client — thin wrapper around Ollama's /api/chat endpoint.

Used by the RAG pipeline to generate code with qwen2.5-coder:3b.
"""

import logging
import time

import requests

logger = logging.getLogger(__name__)


class OllamaChat:
    """Client for Ollama's chat completion API."""

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "qwen2.5-coder:3b",
        timeout: int = 1200,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self._session = requests.Session()

    def health_check(self) -> bool:
        """Check if Ollama is running and the chat model is available."""
        try:
            resp = self._session.get(
                f"{self.base_url}/api/tags",
                timeout=10,
            )
            resp.raise_for_status()
            models = [m["name"] for m in resp.json().get("models", [])]
            available = any(self.model in m for m in models)
            if not available:
                logger.warning(
                    f"Chat model '{self.model}' not found. "
                    f"Available: {models}"
                )
            return available
        except Exception as e:
            logger.error(f"Ollama health check failed: {e}")
            return False

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.7,
        history: list[dict] | None = None,
    ) -> dict:
        """
        Generate a chat completion via Ollama.

        Args:
            system_prompt: System message setting the AI's role and rules.
            user_prompt: User message with the actual request.
            temperature: Sampling temperature (0.0-1.0).
            history: Prior conversation turns as [{"role": "user"|"assistant", "content": ...}].

        Returns:
            Dict with keys: content, model, duration_ms.
            On failure returns dict with content="" and error key.
        """
        messages = [
            {"role": "system", "content": system_prompt},
            *(history or []),
            {"role": "user", "content": user_prompt},
        ]

        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
            },
        }

        start = time.monotonic()

        try:
            resp = self._session.post(
                f"{self.base_url}/api/chat",
                json=payload,
                timeout=self.timeout,
            )
            resp.raise_for_status()
            data = resp.json()

            duration_ms = (time.monotonic() - start) * 1000
            content = data.get("message", {}).get("content", "")

            logger.info(
                f"LLM generation complete: "
                f"{len(content)} chars in {duration_ms:.0f}ms"
            )

            return {
                "content": content,
                "model": self.model,
                "duration_ms": round(duration_ms),
            }

        except requests.exceptions.Timeout:
            duration_ms = (time.monotonic() - start) * 1000
            logger.error(f"LLM generation timed out after {duration_ms:.0f}ms")
            return {
                "content": "",
                "model": self.model,
                "duration_ms": round(duration_ms),
                "error": "Generation timed out",
            }

        except Exception as e:
            duration_ms = (time.monotonic() - start) * 1000
            logger.error(f"LLM generation failed: {e}")
            return {
                "content": "",
                "model": self.model,
                "duration_ms": round(duration_ms),
                "error": str(e),
            }
