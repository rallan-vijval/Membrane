#!/usr/bin/env python3
"""Provider pre‑flight script.
It reads environment variables for the supported providers and runs a lightweight ``probe``
using the public facade defined in ``backend/app/integrations/api.py``.
The script exits with status 0 only if **all** configured providers return ``status == "ok"``.
"""

import os
import sys
import asyncio
from pathlib import Path

# The workspace root for Agent C
ROOT = Path(__file__).resolve().parents[1]  # scratch/membrane_integration
sys.path.append(str(ROOT))  # make ``backend`` importable

from backend.app.integrations.api import EmbeddingConfig, create_embedding_client, probe_provider

PROVIDERS = {
    "OPENAI": {
        "env_key": "OPENAI_API_KEY",
        "default_model": "text-embedding-3-large",
        "default_dimensions": 1536,
    },
    "VOYAGE": {
        "env_key": "VOYAGE_API_KEY",
        "default_model": "voyage-4",
        "default_dimensions": 1024,
    },
}

async def main() -> int:
    semaphore = asyncio.Semaphore(5)
    any_failed = False
    for name, cfg in PROVIDERS.items():
        api_key = os.getenv(cfg["env_key"])
        if not api_key:
            print(f"[✗] {name}: missing environment variable {cfg['env_key']}")
            any_failed = True
            continue
        config = EmbeddingConfig(
            provider=name.lower(),
            model=cfg["default_model"],
            dimensions=cfg["default_dimensions"],
            api_key=api_key,
        )
        result = await probe_provider(config, semaphore)
        status = result["status"]
        if status == "ok":
            print(f"[✓] {name}: ready – profile_id={result['profile_id']}, latency={result.get('latency_ms','?')}ms")
        else:
            print(f"[✗] {name}: {result.get('code','error')} – {result.get('reason','unknown')}")
            any_failed = True
    return 1 if any_failed else 0

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
