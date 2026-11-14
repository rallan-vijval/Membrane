"""Synchronous, bounded provider facade; no application/database imports."""
from __future__ import annotations
from dataclasses import dataclass, field
import hashlib
import math
import time
from typing import Mapping, Any

@dataclass(frozen=True)
class EmbeddingConfig:
    provider: str
    model: str
    dimensions: int
    api_key: str = field(repr=False)
    timeout_seconds: float = 30
    max_retries: int = 1

    def __post_init__(self):
        if self.provider not in {"openai", "voyage"}:
            raise ValueError("Unsupported embedding provider")
        if not self.api_key.strip() or not self.model.strip():
            raise ValueError("Embedding credentials and model are required")
        if not 1 <= self.dimensions <= 4096 or not 0 < self.timeout_seconds <= 120 or self.max_retries not in (0, 1):
            raise ValueError("Invalid embedding limits")

class IntegrationFailure(Exception):
    def __init__(self, code, message, retryable=False, attempted_calls=0):
        super().__init__(message)
        self.code, self.message = code, message
        self.retryable, self.attempted_calls = retryable, attempted_calls

@dataclass
class EmbeddingBatch:
    vectors: list[list[float]]
    profile_id: str
    provider: str
    model: str
    dimensions: int
    input_type: str
    input_tokens: int | None = None
    attempted_calls: int = 0
    elapsed_ms: int = 0

    def __post_init__(self):
        for vector in self.vectors:
            if len(vector) != self.dimensions or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in vector):
                raise ValueError("Invalid embedding vector")

def _profile_id(config):
    value = f"embedding-v1:{config.provider}:{config.model}:{config.dimensions}:document-query"
    return hashlib.sha256(value.encode()).hexdigest()[:24]

class EmbeddingClient:
    def __init__(self, config, semaphore):
        self.config, self.semaphore = config, semaphore
        self.sdk = None

    def describe(self):
        c = self.config
        return {"provider": c.provider, "model": c.model, "dimensions": c.dimensions, "profile_id": _profile_id(c)}

    def embed_documents(self, texts):
        return self._embed(texts, "document")

    def embed_query(self, text):
        return self._embed([text], "query")

    def _embed(self, texts, input_type):
        if not texts or len(texts) > 128 or any(not isinstance(t, str) or not t.strip() for t in texts):
            raise IntegrationFailure("invalid_input", "Embedding input must contain nonempty text")
        start = time.perf_counter()
        for attempt in range(1, self.config.max_retries + 2):
            try:
                with self.semaphore:
                    vectors, tokens = self._request(texts, input_type)
                if len(vectors) != len(texts):
                    raise ValueError("Embedding count mismatch")
                return EmbeddingBatch(vectors=vectors, **self.describe(), input_type=input_type,
                    input_tokens=tokens, attempted_calls=attempt, elapsed_ms=int((time.perf_counter()-start)*1000))
            except Exception as exc:
                status = getattr(exc, "status_code", getattr(exc, "http_status", None))
                retryable = status in (429, 500, 502, 503, 504) or any(word in type(exc).__name__.lower() for word in ("timeout", "connection"))
                if retryable and attempt <= self.config.max_retries:
                    time.sleep(0.1 * attempt)
                    continue
                code = "invalid_response" if isinstance(exc, (ValueError, TypeError)) else ("provider_transient" if retryable else "provider_rejected")
                raise IntegrationFailure(code, "Embedding provider request failed", retryable, attempt) from None

    def probe(self):
        batch = self.embed_query("readiness")
        return {**self.describe(), "usage": {"attempted_calls": batch.attempted_calls, "input_tokens": batch.input_tokens}}

def create_embedding_client(config, semaphore):
    if config.provider == "openai":
        from .provider_openai import OpenAIClient
        return OpenAIClient(config, semaphore)
    from .provider_voyage import VoyageClient
    return VoyageClient(config, semaphore)

def probe_provider(config, semaphore):
    """Explicitly billable: sends one tiny embedding, with at most one retry."""
    try:
        client = create_embedding_client(config, semaphore)
        return {"status": "ok", "code": "ready", **client.probe()}
    except IntegrationFailure as exc:
        return {"status": "error", "code": exc.code, "reason": exc.message,
                "profile_id": _profile_id(config), "usage": {"attempted_calls": exc.attempted_calls}}

@dataclass(frozen=True)
class TracerConfig:
    enabled: bool = False
    api_key: str | None = field(default=None, repr=False)

class NoOpTracer:
    def span(self, name, metadata=None):
        from contextlib import nullcontext
        return nullcontext(self)
    trace_url = None
    def set_outputs(self, outputs):
        pass

def create_tracer(config):
    if not config.enabled:
        return NoOpTracer()
    if not config.api_key:
        raise IntegrationFailure("tracing_key_missing", "Tracing credentials are required")
    from .tracing import LangSmithTracer
    return LangSmithTracer(config.api_key)
