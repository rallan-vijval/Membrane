from __future__ import annotations

import json
import httpx
from .api import EmbeddingClient, IntegrationFailure


class DeepSeekClient(EmbeddingClient):
    """Embedding client for DeepSeek using the public HTTP API.
    The DeepSeek API is compatible with OpenAI's embedding endpoint format.
    """

    def _request(self, texts: list[str], input_type: str):
        # DeepSeek expects a JSON payload similar to OpenAI's embeddings API.
        url = "https://api.deepseek.com/v1/embeddings"
        headers = {"Authorization": f"Bearer {self.config.api_key}", "Content-Type": "application/json"}
        payload = {
            "model": self.config.model,
            "input": texts,
            "dimensions": self.config.dimensions,
        }
        try:
            response = httpx.post(url, headers=headers, json=payload, timeout=self.config.timeout_seconds)
        except Exception as e:
            raise IntegrationFailure("network_error", str(e), retryable=True) from e
        if response.status_code != 200:
            raise IntegrationFailure("provider_error", f"HTTP {response.status_code}: {response.text}", retryable=False)
        data = response.json()
        # Expected format: {"data": [{"embedding": [...], "index": 0}, ...], "usage": {"total_tokens": ...}}
        rows = sorted(data.get("data", []), key=lambda r: r.get("index", 0))
        if [r.get("index") for r in rows] != list(range(len(texts))):
            raise IntegrationFailure("invalid_response", "Embedding indices mismatch", retryable=False)
        embeddings = [r.get("embedding") for r in rows]
        tokens = data.get("usage", {}).get("total_tokens")
        return embeddings, tokens
