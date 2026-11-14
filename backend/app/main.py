from contextlib import asynccontextmanager
from io import BytesIO
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, File, Header, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from PIL import Image, UnidentifiedImageError
from pymongo.errors import PyMongoError
from starlette.exceptions import HTTPException as StarletteHTTPException

from .common import Problem
from .config import Settings
from .models import (ApproveIn, Audio, AudioIn, Candidate, CandidateIn, CandidateList, ErrorResponse,
                     Health, History, QuarantineIn, ReviseIn, Run, RunAccepted, Source, Version,
                     MemoryEntries, RevokeIn, RevokeResult, TaskOptions, ExecuteActiveIn, ActiveExecution)
from .provider import Provider
from .runner import Worker
from .service import Service
from .store import Store
from .voice import Voice


def create_app(settings=None, store=None, provider=None, embeddings=None, tracer=None):
    cfg = settings or Settings()
    store = store or Store(cfg)
    service = Service(store, provider or Provider(cfg), embeddings, tracer)
    worker = Worker(service)
    voice = Voice(service)

    @asynccontextmanager
    async def lifespan(app):
        if cfg.worker_enabled:
            worker.start()
        yield
        worker.stop()
        if store.client:
            store.client.close()

    errors = {status: {"model": ErrorResponse} for status in (404, 409, 422, 429, 502, 503)}
    app = FastAPI(title="Membrane review API", version="1.0.0", lifespan=lifespan, responses=errors)
    app.state.service, app.state.worker = service, worker
    app.add_middleware(CORSMiddleware, allow_origins=[cfg.frontend_origin], allow_methods=["GET", "POST"],
                       allow_headers=["Content-Type", "Idempotency-Key"])

    @app.exception_handler(Problem)
    async def problem_handler(request, exc):
        return JSONResponse(status_code=exc.status, content={"error": {"code": exc.code, "message": exc.message, "details": exc.details}})

    @app.exception_handler(StarletteHTTPException)
    async def http_error_handler(request, exc):
        return JSONResponse(status_code=exc.status_code, content={"error": {"code": "http_error", "message": str(exc.detail), "details": {}}})

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request, exc):
        return JSONResponse(status_code=422, content={"error": {"code": "validation_error", "message": "Request does not match the API contract", "details": {"fields": [list(e["loc"]) for e in exc.errors()]}}})

    @app.exception_handler(PyMongoError)
    async def database_handler(request, exc):
        return JSONResponse(status_code=503, content={"error": {"code": "database_unavailable", "message": "Atlas operation failed; check local configuration and preflight", "details": {}}})

    @app.get("/api/health", response_model=Health)
    def health():
        database = {"status": "unavailable", "reason": "Set MONGODB_URI and run backend preflight"}
        search = {"status": "unavailable", "reason": "Vector Search has not been verified"}
        agent_key = cfg.deepseek_api_key if cfg.llm_provider == "deepseek" else cfg.openai_api_key
        vision_key = cfg.deepseek_api_key if cfg.vision_provider == "deepseek" else cfg.openai_api_key
        embedding_key = cfg.voyage_api_key if cfg.embedding_provider == "voyage" else cfg.openai_api_key
        model = {"status": "degraded" if agent_key.get_secret_value() and cfg.agent_model else "unavailable",
                 "reason": "Configured; verify generation with preflight" if agent_key.get_secret_value() and cfg.agent_model else f"Set {'DEEPSEEK_API_KEY' if cfg.llm_provider == 'deepseek' else 'OPENAI_API_KEY'} and AGENT_MODEL"}
        vision_health = {"status": "degraded" if vision_key.get_secret_value() and cfg.vision_model else "unavailable",
                         "reason": "Configured; verify actual image extraction with preflight" if vision_key.get_secret_value() and cfg.vision_model else f"Set {'DEEPSEEK_API_KEY' if cfg.vision_provider == 'deepseek' else 'OPENAI_API_KEY'} and VISION_MODEL"}
        embedding_health = {"status": "degraded" if embedding_key.get_secret_value() else "unavailable",
                            "reason": "Configured; verify profile/dimensions with preflight" if embedding_key.get_secret_value() else f"Set {'VOYAGE_API_KEY' if cfg.embedding_provider == 'voyage' else 'OPENAI_API_KEY'}"}
        memory_search = {"status": "unavailable" if cfg.governed_memory_enabled else "disabled",
                         "reason": "Memory Search needs initialization and preflight" if cfg.governed_memory_enabled else "Governed memory is disabled"}
        tracing_health = {"status": "degraded" if cfg.langsmith_tracing else "disabled",
                          "reason": "Optional tracing configured; not verified" if cfg.langsmith_tracing else "Optional tracing disabled"}
        if cfg.langsmith_tracing and not cfg.langsmith_api_key.get_secret_value():
            tracing_health = {"status": "unavailable", "reason": "Set LANGSMITH_API_KEY or disable tracing; review remains usable"}
        if cfg.mongodb_uri.get_secret_value() and "<" not in cfg.mongodb_uri.get_secret_value():
            try:
                store.db.command("ping")
                database = {"status": "ready", "reason": "Atlas ping succeeded"}
                state = store.db.workspace_state.find_one(store.query()) or {}
                if not state:
                    database = {"status": "degraded", "reason": "Atlas ping succeeded; run workspace-scoped seed before use"}
                checked = state.get("preflight", {})
                if checked.get("provider_config") == service.provider.config():
                    model = checked.get("model", model)
                    vision_health = checked.get("vision", vision_health)
                    embedding_health = checked.get("embeddings", embedding_health)
                from .selection import index_definition
                try:
                    indexes = list(store.fixtures.list_search_indexes(cfg.fixture_index))
                    if indexes and indexes[0].get("queryable") and indexes[0].get("latestDefinition") == index_definition(cfg.embedding_dimensions):
                        search = {"status": "ready" if checked.get("known_neighbor_passed") else "degraded",
                                  "reason": "Index queryable" + ("; known-neighbor check passed" if checked.get("known_neighbor_passed") else "; run known-neighbor preflight")}
                except Exception:
                    search = {"status": "unavailable", "reason": "Search inspection failed; check Search permissions and preflight"}
                if cfg.governed_memory_enabled:
                    current_profile = None
                    try:
                        current_profile = service.embeddings.describe()["profile_id"]
                        if current_profile != checked.get("profile_id"):
                            embedding_health = {"status": "degraded", "reason": "Current embedding profile needs a new preflight"}
                    except Exception:
                        embedding_health = {"status": "unavailable", "reason": "Embedding facade/configuration is unavailable; integrate Agent C and configure its key"}
                    try:
                        service.memory.require_enabled()
                        service.memory.ensure_index()
                        verified = current_profile is not None and checked.get("profile_id") == current_profile and checked.get("memory_known_neighbor_passed")
                        memory_search = {"status": "ready" if verified else "degraded",
                                         "reason": "Memory index queryable; " + ("known-neighbor passed for current profile" if verified else "run known-neighbor preflight for current profile")}
                    except Exception:
                        memory_search = {"status": "unavailable", "reason": "Governed workspace or memory index not initialized/queryable"}
            except Exception:
                database = {"status": "degraded", "reason": "Atlas ping, initialization, or Search inspection failed; run preflight"}
        voice_health = {"status": "disabled", "reason": "Optional voice is disabled"}
        if cfg.voice_enabled:
            voice_health = {"status": "degraded" if cfg.elevenlabs_api_key.get_secret_value() and cfg.elevenlabs_voice_id else "unavailable",
                            "reason": "Voice configured; account credits and model access unverified" if cfg.elevenlabs_api_key.get_secret_value() and cfg.elevenlabs_voice_id else "Set ELEVENLABS_API_KEY and ELEVENLABS_VOICE_ID"}
        return {"database": database, "model": model, "search": search, "voice": voice_health, "workspace_id": cfg.workspace_id,
                "vision": vision_health, "embeddings": embedding_health, "memory_search": memory_search, "tracing": tracing_health}

    @app.post("/api/sources", response_model=Source, status_code=201)
    async def upload(file: Annotated[UploadFile, File()]):
        data = await file.read(5 * 1024 * 1024 + 1)
        await file.close()
        if len(data) > 5 * 1024 * 1024:
            raise Problem("image_too_large", "Maximum upload is 5 MiB", 422)
        try:
            with Image.open(BytesIO(data)) as image:
                if image.format not in ("PNG", "JPEG") or image.width * image.height > 20_000_000:
                    raise Problem("invalid_image", "Only PNG/JPEG up to 20 megapixels are accepted", 422)
                mime = "image/png" if image.format == "PNG" else "image/jpeg"
                image.verify()
        except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
            raise Problem("invalid_image", "Upload is not a valid PNG/JPEG", 422)
        # Provider and MongoDB operations are synchronous; keep them off the event loop.
        from starlette.concurrency import run_in_threadpool
        return await run_in_threadpool(service.source, data, mime)

    def asset(collection, key, value, media):
        doc = store.get(collection, key, value)
        path = Path(doc.get("local_path", ""))
        if not path.is_file() or not path.resolve().is_relative_to(cfg.data_dir.resolve()):
            raise Problem("asset_missing", "Local asset file is unavailable", 404)
        return FileResponse(path, media_type=media)

    @app.get("/api/sources/{source_id}/image", response_class=FileResponse)
    def image(source_id: str):
        doc = store.get("sources", "source_id", source_id)
        return asset("sources", "source_id", source_id, doc["mime_type"])

    @app.post("/api/candidates", response_model=Candidate, status_code=201)
    def stage(body: CandidateIn):
        return service.stage(body)

    @app.get("/api/candidates", response_model=CandidateList)
    def candidates():
        service.reconcile()
        docs, truncated = store.list("memory_candidates")
        return {"items": [service.public(Candidate, d) for d in docs], "truncated": truncated}

    @app.get("/api/candidates/{candidate_id}", response_model=Candidate)
    def candidate(candidate_id: str):
        service.reconcile()
        return service.public(Candidate, store.get("memory_candidates", "candidate_id", candidate_id))

    @app.get("/api/sources/{source_id}", response_model=Source)
    def source(source_id: str):
        return service.public(Source, store.get("sources", "source_id", source_id))

    @app.post("/api/candidates/{candidate_id}/revise", response_model=Candidate, status_code=201)
    def revise(candidate_id: str, body: ReviseIn):
        return service.revise(candidate_id, body)

    @app.post("/api/candidates/{candidate_id}/runs", response_model=RunAccepted, status_code=202)
    def run(candidate_id: str):
        return service.create_run(candidate_id)

    @app.get("/api/runs/{run_id}", response_model=Run)
    def run_detail(run_id: str):
        return worker.detail(run_id)

    Key = Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=128)]

    @app.post("/api/candidates/{candidate_id}/approve", response_model=Candidate)
    def approve(candidate_id: str, body: ApproveIn, idempotency_key: Key):
        return service.decide(candidate_id, idempotency_key, "approve", body.reason, body.run_id)

    @app.post("/api/candidates/{candidate_id}/quarantine", response_model=Candidate)
    def quarantine(candidate_id: str, body: QuarantineIn, idempotency_key: Key):
        return service.decide(candidate_id, idempotency_key, "quarantine", body.reason)

    @app.get("/api/memory/active", response_model=Version)
    def active():
        service.reconcile()
        return service.public(Version, store.active())

    @app.get("/api/history", response_model=History)
    def history():
        return service.history()

    @app.get("/api/memory/entries", response_model=MemoryEntries)
    def memory_entries():
        return service.memory_entries()

    @app.post("/api/memory/entries/{memory_id}/revoke", response_model=RevokeResult)
    def revoke(memory_id: str, body: RevokeIn, idempotency_key: Key):
        return service.revoke(memory_id, body, idempotency_key)

    @app.get("/api/tasks", response_model=TaskOptions)
    def tasks():
        return service.tasks()

    @app.post("/api/agent/tasks/{fixture_id}/execute", response_model=ActiveExecution, status_code=201)
    def execute_active(fixture_id: str, body: ExecuteActiveIn):
        return service.execute_active(fixture_id, body)

    @app.get("/api/agent/executions/{execution_id}", response_model=ActiveExecution)
    def active_execution(execution_id: str):
        return service.active_execution(execution_id)

    @app.post("/api/runs/{run_id}/cases/{case_id}/audio", response_model=Audio)
    def audio(run_id: str, case_id: str, body: AudioIn):
        return voice.create(run_id, case_id, body)

    @app.get("/api/audio/{audio_id}", response_class=FileResponse)
    def audio_file(audio_id: str):
        return asset("audio_assets", "audio_id", audio_id, "audio/mpeg")

    return app


app = create_app()
