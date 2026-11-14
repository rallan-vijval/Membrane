# Provider integration setup

Use Python 3.12 and install `backend/requirements-dev.txt` (which includes runtime requirements). The runtime includes OpenAI SDK 3.51.0, Voyage 0.6.0 and LangSmith 0.14.17; do not install the old Agent C pins.

Copy `.env.example` into an ignored `.env` in the checkout you will run. Supply MONGODB_URI, DEEPSEEK_API_KEY, and VOYAGE_API_KEY. The default generation and vision provider is DeepSeek, while embeddings use Voyage voyage-4 with 1024 dimensions. OPENAI_API_KEY is needed only when explicitly selecting OpenAI. Atlas plugin authorization does not populate these application credentials. Optional ElevenLabs needs its own key and voice ID; leave VOICE_ENABLED=false initially. Leave LANGSMITH_TRACING=false for the first check.

From the repository root:

```powershell
python scripts/provider_preflight.py
python scripts/backend_setup.py seed --with-embeddings
python scripts/backend_setup.py index
python scripts/backend_setup.py preflight
```

These are live operations. The provider preflight sends one tiny embedding, at most one retry. Seeding writes only the configured workspace and makes embedding calls; index creation needs Atlas permissions. Wait for both indexes to become queryable and rerun preflight. Full preflight checks actual generation, image extraction, embeddings and both known-neighbor searches. A failure is a failure; there is no synthetic fallback.

The synchronous facade uses a shared thread semaphore, explicit SDK clients, disabled SDK retries, at most one facade retry for transient failures, explicit dimensions and Voyage document/query conventions. Profiles include conventions/version as well as provider/model/dimensions. Changing a profile requires re-embedding in an isolated workspace. Error messages omit raw provider responses and credentials.

Optional LangSmith exports only an allowlist of identifiers/status/counters on a bounded daemon queue, with no prompts or documents. Delivery is best effort; pending spans may be lost on shutdown. Trace URLs remain null. Tracing failure never changes business results. No live tracing delivery has been verified yet.

Official references: https://docs.voyageai.com/docs/embeddings and https://api-docs.deepseek.com/guides/responses_api/.
