---
# Integration Setup Documentation (Agent C)

## Overview
This document explains how to install, configure, and validate the **embedding provider integration** that Agent C supplies for the Membrane project.
It covers:
* required environment variables
* Python dependencies
* the pre‑flight script
* error‑code reference
* optional LangSmith tracing configuration

---
## 1. Environment Variables
| Variable | Provider | Description |
|----------|----------|-------------|
| `OPENAI_API_KEY` | OpenAI | Secret key for the OpenAI embeddings endpoint. |
| `VOYAGE_API_KEY` | Voyage | Secret key for Voyage embeddings. |
| `LANGSMITH_TRACING` | – | Set to `true` (case‑insensitive) to enable optional tracing. Default is `false`. |
| `LANGSMITH_API_KEY` | – | API key required when tracing is enabled. |

All variables are read **by the caller** (Agent A). The integration package receives an explicit `EmbeddingConfig` – it never reads env vars itself.

---
## 2. Installation
```bash
# from the repository root (scratch workspace)
cd /Users/amirh/.gemini/antigravity/scratch/membrane_integration
pip install -r backend/requirements-integrations.txt
```
The file pins the exact SDK versions used:
```
openai==1.30.0
voyageai==0.2.3
```
Test‑only dependencies (`pytest`, `pytest‑asyncio`, `responses`) are also installed.

---
## 3. Running the Pre‑flight Script
The script checks that each configured provider can be contacted and that the requested dimensions are available.
```bash
python scripts/provider_preflight.py
```
**Exit codes**
* `0` – all providers returned `status: ok`.
* `1` – one or more providers failed (missing env var, auth error, dimension mismatch, network error, …).

The output looks like:
```
[✓] OPENAI: ready – profile_id=abc123def456, latency=42ms
[✗] VOYAGE: auth_error – invalid API key
```
---
## 4. Public Facade (`backend/app/integrations/api.py`)
The facade provides the following stable objects:
* `EmbeddingConfig` – immutable configuration, redacted ``api_key``.
* `create_embedding_client(config, semaphore)` – returns an `EmbeddingClient` supporting OpenAI or Voyage.
* `probe_provider(config, semaphore)` – returns a dict:
  ```json
  {
    "status": "ok"|"error",
    "code": "ready"|"auth_error"|"network_error"|"dimension_mismatch"|"unknown",
    "reason": "human readable message",
    "profile_id": "12‑char sha256",
    "provider": "openai"|"voyage",
    "model": "...",
    "dimensions": 1536|1024,
    "usage": {"prompt_tokens": 1, ...} | null,
    "latency_ms": 57
  }
  ```
* `EmbeddingBatch`, `IntegrationFailure`, and the optional `Tracer` (controlled by `TracerConfig`).

---
## 5. Error‑Code Reference
| Code | Meaning | Retryable? |
|------|---------|------------|
| `auth_error` | Invalid or missing API key. | No |
| `network_error` | Transient network failure after retries. | No (retries already applied) |
| `dimension_mismatch` | Provider returned a vector of unexpected length. | No |
| `input_too_long` | Text exceeded provider limits. | No |
| `provider_unknown` | Requested provider not supported by the facade. | No |
| `tracing_key_missing` | LangSmith tracing enabled but key not supplied. | No |
| `unknown` | Unexpected exception – sanitized. | No |

---
## 6. Optional LangSmith Tracing
When `LANGSMITH_TRACING=true` and a valid `LANGSMITH_API_KEY` are present, `create_tracer` returns a lightweight wrapper that records spans.
* The tracer is **no‑op** when tracing is disabled.
* Tracing never changes the result of any embedding call and never raises to the caller.
* Only redacted metadata is sent; the raw prompt or API keys are never included.

---
## 7. Testing (CI)
Running the test suite validates the integration in isolation:
```bash
pytest backend/integrations_tests
```
The suite uses mocked SDK responses, so no real network calls are performed. It checks:
* successful embedding and dimension validation
* proper handling of authentication errors
* semaphore usage (max concurrent calls = 5)
* that `probe_provider` returns the expected structured dict
* that the optional tracer behaves as a no‑op when disabled

---
## 8. Updating the Integration
If a breaking change is required (e.g., new method signatures), coordinate with Agent A to bump the version and update the contract. Additive changes (new helper functions, extra optional fields) can be introduced without a version bump.

---
*Prepared by Agent C – ready for review and merge.*