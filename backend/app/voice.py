import time

import httpx
from pymongo.errors import DuplicateKeyError

from .common import Problem, digest
from .models import Audio


class Voice:
    def __init__(self, service):
        self.service, self.store = service, service.store

    def create(self, run_id, case_id, body):
        s, cfg = self.store, self.store.settings
        if not cfg.voice_enabled or not cfg.elevenlabs_api_key.get_secret_value() or not cfg.elevenlabs_voice_id:
            raise Problem("voice_unavailable", "Configure and enable ElevenLabs voice first", 503)
        run = s.get("evaluation_runs", "run_id", run_id)
        execution = s.db.case_results.find_one(s.query(run_id=run_id, case_id=case_id, side=body.side, repetition=body.repetition))
        if not execution or execution["error"] or not execution["attempt"]:
            raise Problem("audio_evidence_missing", "A completed stored answer is required", 409)
        text = execution["attempt"]["answer"]
        if not text or len(text) > cfg.max_tts_characters_per_request:
            raise Problem("audio_length", "Stored answer is empty or exceeds configured speech length limit", 422)
        settings = {"stability": 0.5, "similarity_boost": 0.75, "style": 0.0, "use_speaker_boost": True}
        audio_id = "audio_" + digest({"workspace": s.workspace, "text": text, "provider": "elevenlabs",
            "model": cfg.elevenlabs_tts_model, "voice": cfg.elevenlabs_voice_id, "settings": settings})
        prior = s.db.audio_assets.find_one(s.query(audio_id=audio_id))
        if prior:
            if prior["status"] != "ready":
                raise Problem("audio_pending_or_failed", "Speech generation is pending or previously failed; inspect voice service", 503)
            return {"audio_id": audio_id, "audio_url": f"/api/audio/{audio_id}", "transcript": text, "cached": True}
        doc = s.doc(audio_id=audio_id, status="generating", transcript=text, characters=len(text), settings=settings,
                    model=cfg.elevenlabs_tts_model, voice=cfg.elevenlabs_voice_id, run_id=run_id, case_id=case_id)
        try:
            s.db.audio_assets.insert_one(doc)
        except DuplicateKeyError:
            raise Problem("audio_pending", "Speech is already being generated", 409)
        quota = s.db.workspace_state.update_one(s.query(voice_characters={"$lte": cfg.max_tts_characters_total - len(text)}),
                                               {"$inc": {"voice_characters": len(text)}})
        if quota.modified_count != 1:
            s.db.audio_assets.update_one(s.query(audio_id=audio_id), {"$set": {"status": "failed", "error": "quota_exhausted"}})
            raise Problem("voice_quota", "Local speech character budget exhausted", 429)
        start = time.monotonic()
        try:
            with httpx.Client(timeout=cfg.model_timeout_seconds) as client:
                response = client.post(f"https://api.elevenlabs.io/v1/text-to-speech/{cfg.elevenlabs_voice_id}",
                    params={"output_format": "mp3_44100_128"}, headers={"xi-api-key": cfg.elevenlabs_api_key.get_secret_value()},
                    json={"text": text, "model_id": cfg.elevenlabs_tts_model, "voice_settings": settings})
                response.raise_for_status()
            path = cfg.data_dir / "audio" / f"{audio_id}.mp3"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(response.content)
            s.db.audio_assets.update_one(s.query(audio_id=audio_id), {"$set": {"status": "ready", "local_path": str(path),
                "provider_request_id": response.headers.get("request-id"), "reported_characters": response.headers.get("character-cost"),
                "latency_ms": int((time.monotonic() - start) * 1000)}})
        except Exception:
            s.db.audio_assets.update_one(s.query(audio_id=audio_id), {"$set": {"status": "failed", "error": "provider_or_storage_error"}})
            raise Problem("voice_failed", "Speech provider or audio storage failed; review remains usable", 502)
        return {"audio_id": audio_id, "audio_url": f"/api/audio/{audio_id}", "transcript": text, "cached": False}
