"""Agent A's application wiring. Agent C owns the imported integrations facade."""
from contextlib import contextmanager
from threading import BoundedSemaphore

from .common import Problem


class Embeddings:
    def __init__(self, settings, semaphore=None):
        self.settings = settings
        self.semaphore = semaphore or BoundedSemaphore(settings.max_concurrent_model_calls)
        self._client = None

    @property
    def client(self):
        if self._client is None:
            try:
                from .integrations.api import EmbeddingConfig, create_embedding_client
            except ImportError:
                raise Problem("integration_unavailable", "Agent C embedding facade has not been integrated", 503)
            key = self.settings.voyage_api_key if self.settings.embedding_provider == "voyage" else self.settings.openai_api_key
            try:
                config = EmbeddingConfig(provider=self.settings.embedding_provider, model=self.settings.embedding_model,
                    dimensions=self.settings.embedding_dimensions, api_key=key.get_secret_value(),
                    timeout_seconds=self.settings.model_timeout_seconds, max_retries=1)
                self._client = create_embedding_client(config, self.semaphore)
            except Exception:
                raise Problem("embedding_unavailable", "Embedding configuration is unavailable or incompatible", 503)
        return self._client

    def describe(self):
        try:
            return self.client.describe()
        except Problem:
            raise
        except Exception:
            raise Problem("embedding_unavailable", "Embedding profile could not be described", 503)

    def invoke(self, method, value):
        try:
            return getattr(self.client, method)(value)
        except Problem:
            raise
        except Exception as exc:
            count = getattr(exc, "attempted_calls", 0)
            count = count if isinstance(count, int) and 0 <= count <= 2 else 0
            raise Problem("embedding_unavailable", "Embedding request failed; check provider readiness", 503, attempted_calls=count)

    def embed_query(self, text):
        return self.invoke("embed_query", text)

    def embed_documents(self, texts):
        return self.invoke("embed_documents", texts)


class TraceHandle:
    def __init__(self, inner=None):
        self.inner = inner

    @property
    def trace_url(self):
        try:
            value = getattr(self.inner, "trace_url", None)
            return value if isinstance(value, str) and value.startswith("https://") else None
        except Exception:
            return None

    def set_outputs(self, metadata):
        try:
            if self.inner:
                self.inner.set_outputs(metadata)
        except Exception:
            pass


class SafeTracing:
    def __init__(self, settings, tracer=None):
        self.settings, self.tracer = settings, tracer

    @contextmanager
    def span(self, name, metadata):
        # Missing optional instrumentation must never block or retry business work.
        if self.tracer is None and self.settings.langsmith_tracing:
            try:
                from .integrations.api import create_tracer
                self.tracer = create_tracer({"enabled": True, "api_key": self.settings.langsmith_api_key.get_secret_value()})
            except Exception:
                self.tracer = None
        context, handle = None, TraceHandle()
        if self.tracer:
            try:
                context = self.tracer.span(name, metadata)
                handle = TraceHandle(context.__enter__())
            except Exception:
                context = None
        try:
            yield handle
        finally:
            if context:
                try:
                    context.__exit__(None, None, None)
                except Exception:
                    pass
