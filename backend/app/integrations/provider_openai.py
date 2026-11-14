"""OpenAI embedding client implementation for Agent C.
It conforms to the ``EmbeddingClient`` protocol defined in ``backend/app/integrations/api.py``.
The client only uses the official ``openai`` Python package; the import is lazy so the module can be imported even when the package is absent (e.g., during CI where we mock the SDK).
"""

from __future__ import annotations
import asyncio
import time
from typing import List, Mapping, Any

from .api import EmbeddingConfig, EmbeddingBatch, IntegrationFailure, _run_with_semaphore


class OpenAIClient:
    """Concrete ``EmbeddingClient`` for the OpenAI provider.

    * ``embed_documents`` – batch embedding of many texts.
    * ``embed_query`` – single‑text embedding (returns a batch with one vector).
    * ``describe`` – returns a static description of capabilities.
    * ``probe`` – performs a cheap call (embeds a single token) to verify credentials and dimensions.
    """

    def __init__(self, config: EmbeddingConfig, semaphore: asyncio.Semaphore):
        self.config = config
        self.semaphore = semaphore
        # Import lazily – the real ``openai`` package may be missing in the test environment.
        try:
            import openai
            self._openai = openai
        except Exception as exc:  # pragma: no cover
            raise IntegrationFailure(
                code="sdk_missing",
                message="openai SDK not installed",
                retryable=False,
                attempted_calls=0,
            ) from exc
        # Apply API key at runtime – ``openai.api_key`` is the canonical location.
        self._openai.api_key = config.api_key
        # Timeout handling – ``openai`` uses ``request_timeout`` argument.
        self.timeout = config.timeout_seconds
        self.max_retries = max(0, config.max_retries)

    # ---------------------------------------------------------------------
    # Helper to invoke the SDK with retry / semaphore handling
    # ---------------------------------------------------------------------
    async def _call(self, coro, attempt: int = 1):
        try:
            return await _run_with_semaphore(self.semaphore, coro)
        except Exception as exc:  # pragma: no cover – SDK network error handling
            if attempt <= self.max_retries:
                await asyncio.sleep(0.2)  # tiny back‑off before retry
                return await self._call(coro, attempt + 1)
            raise IntegrationFailure(
                code="network_error",
                message=str(exc),
                retryable=False,
                attempted_calls=attempt,
            ) from exc

    async def embed_documents(self, texts: List[str]) -> EmbeddingBatch:
        if not texts:
            raise IntegrationFailure(code="empty_input", message="no texts provided", retryable=False)
        # OpenAI expects ``input`` list and ``model``.
        coro = self._openai.Embedding.acreate(
            model=self.config.model,
            input=texts,
            request_timeout=self.timeout,
        )
        result = await self._call(coro)
        # Result format (as of openai>=1.0): {"data": [{"embedding": [...]}], "usage": {...}}
        vectors = [item["embedding"] for item in result.get("data", [])]
        usage = result.get("usage", {})
        batch = EmbeddingBatch(
            vectors=vectors,
            profile_id=self._profile_id(),
            provider=self.config.provider,
            model=self.config.model,
            dimensions=self.config.dimensions,
            input_type="document",
            input_tokens=usage.get("prompt_tokens"),
            attempted_calls=1,
            elapsed_ms=int((time.time() - result.get("_request_timestamp", time.time())) * 1000),
        )
        # Validate dimensions
        for v in vectors:
            if len(v) != self.config.dimensions:
                raise IntegrationFailure(
                    code="dimension_mismatch",
                    message=f"expected {self.config.dimensions}, got {len(v)}",
                    retryable=False,
                )
        return batch

    async def embed_query(self, text: str) -> EmbeddingBatch:
        return await self.embed_documents([text])

    def describe(self) -> Mapping[str, Any]:
        return {
            "provider": self.config.provider,
            "model": self.config.model,
            "dimensions": self.config.dimensions,
            "capabilities": ["embed_documents", "embed_query"],
        }

    async def probe(self) -> Mapping[str, Any]:
        """Light health check – embed a single short token.
        The OpenAI API returns usage information even for tiny calls.
        """
        # A single word is guaranteed to be under the token limit.
        try:
            result = await self._call(
                self._openai.Embedding.acreate(
                    model=self.config.model,
                    input=["probe"],
                    request_timeout=self.timeout,
                )
            )
        except IntegrationFailure as e:
            raise e
        usage = result.get("usage", {})
        return {"usage": usage}

    # -----------------------------------------------------------------
    def _profile_id(self) -> str:
        import hashlib
        s = f"{self.config.provider}:{self.config.model}:{self.config.dimensions}"
        return hashlib.sha256(s.encode()).hexdigest()[:12]
