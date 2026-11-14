# Integration public facade (stable API)
"""backend/app/integrations/api.py
Public interface for embedding providers used by Agent A.
All functions are pure Python and do **not** import FastAPI, settings, or database code.
"""

from __future__ import annotations
import asyncio
import time
from dataclasses import dataclass, field
from typing import List, Protocol, Any, Mapping, Optional

# --------------------------
# Data structures
# --------------------------

@dataclass(frozen=True, slots=True)
class EmbeddingConfig:
    """Immutable configuration for a provider.
    The ``api_key`` is stored but its ``repr`` is redacted.
    """

    provider: str
    model: str
    dimensions: int
    api_key: str = field(repr=False)
    timeout_seconds: int = 30
    max_retries: int = 1

    def __post_init__(self) -> None:
        if self.dimensions <= 0:
            raise ValueError("dimensions must be positive")


@dataclass(slots=True)
class EmbeddingBatch:
    vectors: List[List[float]]
    profile_id: str
    provider: str
    model: str
    dimensions: int
    input_type: str  # "document" or "query"
    input_tokens: Optional[int] = None
    attempted_calls: int = 0
    elapsed_ms: int = 0

    def __post_init__(self) -> None:
        # basic sanity
        for v in self.vectors:
            if len(v) != self.dimensions:
                raise ValueError("vector dimension mismatch")


@dataclass(frozen=True, slots=True)
class IntegrationFailure:
    code: str
    message: str
    retryable: bool = False
    attempted_calls: int = 1

    def __str__(self) -> str:
        return f"IntegrationFailure({self.code}: {self.message})"


# --------------------------
# Provider client protocol
# --------------------------

class EmbeddingClient(Protocol):
    async def embed_documents(self, texts: List[str]) -> EmbeddingBatch: ...
    async def embed_query(self, text: str) -> EmbeddingBatch: ...
    def describe(self) -> Mapping[str, Any]: ...
    async def probe(self) -> Mapping[str, Any]: ...


# --------------------------
# Factory
# --------------------------

async def _run_with_semaphore(semaphore: asyncio.Semaphore, coro):
    async with semaphore:
        return await coro


def create_embedding_client(config: EmbeddingConfig, semaphore: asyncio.Semaphore) -> EmbeddingClient:
    """Return a concrete client for the requested provider.
    Currently supports ``openai`` and ``voyage``.
    """
    if config.provider == "openai":
        from .provider_openai import OpenAIClient
        return OpenAIClient(config, semaphore)
    elif config.provider == "voyage":
        from .provider_voyage import VoyageClient
        return VoyageClient(config, semaphore)
    else:
        raise IntegrationFailure(code="provider_unknown", message=f"{config.provider} not supported", retryable=False)


# --------------------------
# Tracing (optional LangSmith)
# --------------------------

@dataclass(frozen=True, slots=True)
class TracerConfig:
    enabled: bool = False
    api_key: Optional[str] = None

class NoOpTracer:
    def span(self, name: str, metadata: Mapping[str, Any] | None = None):
        class Dummy:
            def __enter__(self):
                return self
            def __exit__(self, exc_type, exc, tb):
                return False
            def set_outputs(self, _: Mapping[str, Any]):
                pass
        return Dummy()


def create_tracer(config: TracerConfig):
    """Return a tracer object.
    When ``enabled`` is False a no‑op implementation is returned.
    """
    if not config.enabled:
        return NoOpTracer()
    # Minimal LangSmith wrapper – avoid importing heavy libraries here.
    class LangSmithTracer:
        def __init__(self, api_key: str):
            self.api_key = api_key
        def span(self, name: str, metadata: Mapping[str, Any] | None = None):
            # Simple context manager that records metadata.
            class Handle:
                def __enter__(self_inner):
                    self_inner.start = time.time()
                    self_inner.metadata = metadata or {}
                    return self_inner
                def __exit__(self_inner, exc_type, exc, tb):
                    self_inner.elapsed = time.time() - self_inner.start
                    # In real implementation we would POST to LangSmith here.
                    return False
                def set_outputs(self_inner, outputs: Mapping[str, Any]):
                    self_inner.outputs = outputs
            return Handle()
    if not config.api_key:
        raise IntegrationFailure(code="tracing_key_missing", message="LangSmith API key not provided", retryable=False)
    return LangSmithTracer(config.api_key)


# --------------------------
# Probe helper (used by Agent A for readiness)
# --------------------------

def _profile_id(config: EmbeddingConfig) -> str:
    # Deterministic identifier used for compatibility checks.
    import hashlib
    s = f"{config.provider}:{config.model}:{config.dimensions}"
    return hashlib.sha256(s.encode()).hexdigest()[:12]

async def probe_provider(config: EmbeddingConfig, semaphore: asyncio.Semaphore) -> Mapping[str, Any]:
    """Light health check – no paid calls, just validates credentials and dimensions.
    Returns a dict with ``status`` ("ok"/"error"), ``code``, ``reason``, ``profile_id`` and optional ``usage``.
    """
    client = create_embedding_client(config, semaphore)
    try:
        start = time.time()
        # ``probe`` is provider‑specific; we fallback to a tiny embed of a single word.
        result = await _run_with_semaphore(semaphore, client.probe())
        latency = (time.time() - start) * 1000
        return {
            "status": "ok",
            "code": "ready",
            "reason": "provider reachable",
            "profile_id": _profile_id(config),
            "provider": config.provider,
            "model": config.model,
            "dimensions": config.dimensions,
            "usage": result.get("usage"),
            "latency_ms": int(latency),
        }
    except IntegrationFailure as e:
        return {
            "status": "error",
            "code": e.code,
            "reason": e.message,
            "profile_id": _profile_id(config),
            "provider": config.provider,
            "model": config.model,
            "dimensions": config.dimensions,
            "usage": None,
            "latency_ms": None,
        }
    except Exception as exc:  # pragma: no cover – unexpected
        return {
            "status": "error",
            "code": "unknown",
            "reason": str(exc),
            "profile_id": _profile_id(config),
            "provider": config.provider,
            "model": config.model,
            "dimensions": config.dimensions,
            "usage": None,
            "latency_ms": None,
        }
