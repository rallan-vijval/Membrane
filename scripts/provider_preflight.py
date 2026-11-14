"""Explicitly billable check of the selected embedding provider only."""
import json
import sys
from pathlib import Path
from threading import BoundedSemaphore
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.app.config import Settings
from backend.app.integrations.api import EmbeddingConfig, probe_provider

def main():
    settings = Settings()
    key = settings.voyage_api_key if settings.embedding_provider == "voyage" else settings.openai_api_key
    try:
        config = EmbeddingConfig(provider=settings.embedding_provider, model=settings.embedding_model, dimensions=settings.embedding_dimensions, api_key=key.get_secret_value())
        result = probe_provider(config, BoundedSemaphore(2))
    except Exception:
        result = {"status": "error", "code": "configuration_unavailable"}
    print(json.dumps(result))
    return 0 if result["status"] == "ok" else 1
if __name__ == "__main__":
    sys.exit(main())
