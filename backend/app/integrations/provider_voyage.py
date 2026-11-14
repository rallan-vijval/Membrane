"""Voyage embedding client implementation for Agent C.
Implements the same ``EmbeddingClient`` protocol as ``provider_openai.py`` but uses the official ``voyageai`` SDK.
"""

from __future__ import annotations
import asyncio
import time
from typing import List, Mapping, Any

from .api import EmbeddingConfig, EmbeddingBatch, IntegrationFailure, _run_with_semaphore


class VoyageClient:
    """Concrete ``EmbeddingClient`` for the Voyage provider.

    Supported models:
    - ``voyage-4`` (1024‑dimensional) – used for both document and query embeddings.
    """

    def __init__(self, config: EmbeddingConfig, semaphore: asyncio.Semaphore):
        self.config = config
        self.semaphore = semaphore
        try:
            import voyageai
            self._voyage = voyageai
        except Exception as exc:  # pragma: no cover
            raise IntegrationFailure(
                code="sdk_missing",
                message="voyageai SDK not installed",
                retryable=False,
                attempted_calls=0,
            ) from exc
        # Apply API key at runtime – the SDK expects ``api_key`` attribute.
        self._voyage.api_key = config.api_key
        self.timeout = config.timeout_seconds
        self.max_retries = max(0, config.max_retries)

    async def _call(self, coro, attempt: int = 1):
        try:
            return await _run_with_semaphore(self.semaphore, coro)
        except Exception as exc:  # pragma: no cover – network errors
            if attempt <= self.max_retries:
                await asyncio.sleep(0.2)
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
        # Voyage SDK expects ``model`` and ``input_type``.
        coro = self._voyage.embeddings.create(
            model=self.config.model,
            input=texts,
            input_type="document",
            timeout=self.timeout,
        )
        result = await self._call(coro)
        # Result format: {"data": [{"embedding": [...] }], "usage": {...}}
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
        for v in vectors:
            if len(v) != self.config.dimensions:
                raise IntegrationFailure(
                    code="dimension_mismatch",
                    message=f"expected {self.config.dimensions}, got {len(v)}",
                    retryable=False,
                )
        return batch

    async def embed_query(self, text: str) -> EmbeddingBatch:
        if not text:
            raise IntegrationFailure(code="empty_input", message="no text provided", retryable=False)
        coro = self._voyage.embeddings.create(
            model=self.config.model,
            input=[text],
            input_type="query",
            timeout=self.timeout,
        )
        result = await self._call(coro)
        vectors = [item["embedding"] for item in result.get("data", [])]
        usage = result.get("usage", {})
        batch = EmbeddingBatch(
            vectors=vectors,
            profile_id=self._profile_id(),
            provider=self.config.provider,
            model=self.config.model,
            dimensions=self.config.dimensions,
            input_type="query",
            input_tokens=usage.get("prompt_tokens"),
            attempted_calls=1,
            elapsed_ms=int((time.time() - result.get("_request_timestamp", time.time())) * 1000),
        )
        for v in vectors:
            if len(v) != self.config.dimensions:
                raise IntegrationFailure(
                    code="dimension_mismatch",
                    message=f"expected {self.config.dimensions}, got {len(v)}",
                    retryable=False,
                )
        return batch

    def describe(self) -> Mapping[str, Any]:
        return {
            "provider": self.config.provider,
            "model": self.config.model,
            "dimensions": self.config.dimensions,
            "capabilities": ["embed_documents", "embed_query"],
        }

    async def probe(self) -> Mapping[str, Any]:
        """Light health check – embed a short token.
        Voyage returns usage information in the response.
        """
        try:
            result = await self._call(
                self._voyage.embeddings.create(
                    model=self.config.model,
                    input=["probe"],
                    input_type="document",
                    timeout=self.timeout,
                )
            )
        except IntegrationFailure as e:
            raise e
        usage = result.get("usage", {})
        return {"usage": usage}

    def _profile_id(self) -> str:
        import hashlib
        s = f"{self.config.provider}:{self.config.model}:{self.config.dimensions}"
        return hashlib.sha256(s.encode()).hexdigest()[:12]
