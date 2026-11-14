"""Untrusted audio intake; bounded batch transcription, never authority or admission."""
import hashlib
import json
import math
import subprocess
import tempfile
from pathlib import Path
from threading import BoundedSemaphore
from datetime import datetime, timezone

import httpx
from pymongo.errors import DuplicateKeyError

from .common import Problem, digest, now, uid
from .models import AudioSource, AudioWord, Source


class AudioSources:
    def __init__(self, service):
        self.service, self.store = service, service.store
        self.semaphore = BoundedSemaphore(1)

    def indexes(self):
        for collection in ("audio_sources", "audio_reviews"):
            self.store.db[collection].create_index([("workspace_id", 1), ("request_key", 1)], unique=True)

    def get(self, audio_id):
        doc = self.store.get("audio_sources", "audio_source_id", audio_id)
        if doc["status"] == "processing" and (datetime.now(timezone.utc) - datetime.fromisoformat(doc["created_at"])).total_seconds() > 180:
            self.store.db.audio_sources.update_one(self.store.query(audio_source_id=audio_id, status="processing"),
                {"$set": {"status": "failed", "error": "interrupted_transcription"}})
            doc = self.store.get("audio_sources", "audio_source_id", audio_id)
        return self.service.public(AudioSource, doc)

    def normalize(self, data):
        cfg = self.store.settings
        if not data or len(data) > cfg.max_audio_bytes:
            raise Problem("audio_size", "Audio must be nonempty and at most 10 MiB", 422)
        try:
            cfg.data_dir.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(dir=cfg.data_dir) as directory:
                source, output = Path(directory) / "input.bin", Path(directory) / "normalized.wav"
                source.write_bytes(data)
                probe = subprocess.run([cfg.ffprobe_path, "-v", "error", "-protocol_whitelist", "file,pipe",
                    "-show_entries", "format=duration,format_name:stream=codec_type", "-of", "json", str(source)],
                    capture_output=True, timeout=15, check=True)
                info = json.loads(probe.stdout)
                duration = float(info["format"]["duration"]) if info["format"].get("duration") not in (None, "N/A") else None
                formats = set(info["format"]["format_name"].split(","))
                if not formats.intersection({"wav", "mp3", "mov", "mp4", "m4a", "ogg", "matroska", "webm"}):
                    raise ValueError("Unsupported container")
                if any(s["codec_type"] == "video" for s in info.get("streams", [])):
                    raise ValueError("Audio only")
                if duration is not None and (not math.isfinite(duration) or not 0.1 <= duration <= cfg.max_audio_seconds):
                    raise ValueError("Duration outside limit")
                subprocess.run([cfg.ffmpeg_path, "-v", "error", "-nostdin", "-protocol_whitelist", "file,pipe", "-i", str(source),
                    "-map", "0:a:0", "-vn", "-t", str(cfg.max_audio_seconds + 1), "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(output)],
                    capture_output=True, timeout=20, check=True)
                import wave
                with wave.open(str(output), "rb") as decoded:
                    measured = decoded.getnframes() / decoded.getframerate()
                if not 0.1 <= measured <= cfg.max_audio_seconds:
                    raise ValueError("Decoded duration outside limit")
                return output.read_bytes(), measured
        except FileNotFoundError:
            raise Problem("audio_tools_missing", "Install ffmpeg and ffprobe or configure their paths", 503) from None
        except Exception:
            raise Problem("audio_invalid", "Use a valid audio-only clip between 0.1 and 120 seconds", 422) from None

    def transcribe(self, wav):
        cfg = self.store.settings
        with httpx.Client(timeout=cfg.transcription_timeout_seconds) as client:
            response = client.post("https://api.elevenlabs.io/v1/speech-to-text",
                headers={"xi-api-key": cfg.elevenlabs_api_key.get_secret_value()},
                files={"file": ("source.wav", wav, "audio/wav")},
                data={"model_id": cfg.transcription_model, "timestamps_granularity": "word",
                      "diarize": "false", "tag_audio_events": "false", "webhook": "false"})
            response.raise_for_status()
            data = response.json()
        text = data.get("text", "")
        if not isinstance(text, str) or not text.strip() or len(text) > 16000:
            raise Problem("no_speech", "No usable speech was transcribed; record a clearer note", 422)
        words = []
        for word in data.get("words", []):
            if word.get("type") != "word":
                continue
            item = AudioWord.model_validate({k: word[k] for k in ("text", "start", "end")})
            if not math.isfinite(item.start) or not math.isfinite(item.end) or item.end < item.start:
                raise ValueError("Invalid timestamps")
            words.append(item.model_dump())
        return text, words, data.get("language_code"), response.headers.get("request-id")

    def create(self, data, key):
        cfg, s = self.store.settings, self.store
        if not cfg.transcription_enabled or not cfg.elevenlabs_api_key.get_secret_value():
            raise Problem("transcription_unavailable", "Enable transcription and configure ELEVENLABS_API_KEY", 503)
        sha = hashlib.sha256(data).hexdigest()
        self.indexes()
        prior = s.db.audio_sources.find_one(s.query(request_key=key))
        if prior:
            if prior["sha256"] != sha:
                raise Problem("idempotency_conflict", "This key belongs to another upload")
            return self.get(prior["audio_source_id"])
        if not self.semaphore.acquire(blocking=False):
            raise Problem("transcription_busy", "Another transcription is in progress; try again later", 429)
        try:
            wav, duration = self.normalize(data)
            audio_id = uid("audio_source")
            folder = cfg.data_dir / "audio-sources" / audio_id
            folder.mkdir(parents=True)
            original, playable = folder / "original.bin", folder / "playback.wav"
            original.write_bytes(data)
            playable.write_bytes(wav)
            doc = s.doc(audio_source_id=audio_id, request_key=key, created_request_at=now(), sha256=sha,
                duration_seconds=duration, audio_url=f"/api/audio-sources/{audio_id}/audio", status="processing",
                model=cfg.transcription_model, transcript="", words=[], language=None, error=None, trust="untrusted",
                local_path=str(playable), original_path=str(original))
            try:
                s.db.audio_sources.insert_one(doc)
            except DuplicateKeyError:
                prior = s.db.audio_sources.find_one(s.query(request_key=key))
                if prior["sha256"] != sha:
                    raise Problem("idempotency_conflict", "This key belongs to another upload")
                return self.get(prior["audio_source_id"])
            reserved = s.db.workspace_state.update_one(s.query(**{"$or": [
                {"transcription_seconds": {"$exists": False}},
                {"transcription_seconds": {"$lte": cfg.max_transcription_seconds_total - duration}}]}),
                {"$inc": {"transcription_seconds": duration}}) if duration <= cfg.max_transcription_seconds_total else None
            if not reserved or reserved.modified_count != 1:
                s.db.audio_sources.update_one(s.query(audio_source_id=audio_id), {"$set": {"status": "failed", "error": "transcription_budget"}})
                return self.get(audio_id)
            try:
                text, words, language, request_id = self.transcribe(wav)
                if any(w["end"] > duration + 1 for w in words):
                    raise ValueError("Timestamp outside recording")
                changes = dict(status="transcribed", transcript=text, words=words, language=language, provider_request_id=request_id)
            except Exception as exc:
                code = "transcription_failed"
                if isinstance(exc, Problem):
                    code = exc.code
                elif isinstance(exc, httpx.TimeoutException):
                    code = "transcription_timeout"
                elif isinstance(exc, httpx.HTTPStatusError):
                    code = {401: "transcription_authentication", 403: "transcription_permission", 402: "transcription_credits",
                            429: "transcription_rate_limit"}.get(exc.response.status_code, "transcription_provider_rejected")
                elif isinstance(exc, (ValueError, TypeError, KeyError)):
                    code = "transcription_invalid_response"
                changes = dict(status="failed", error=code, attempted_calls=1)
            s.db.audio_sources.update_one(s.query(audio_source_id=audio_id), {"$set": {**changes, "attempted_calls": 1}})
            return self.get(audio_id)
        finally:
            self.semaphore.release()

    def review(self, audio_id, text, key):
        s = self.store
        self.indexes()
        audio = s.get("audio_sources", "audio_source_id", audio_id)
        if audio["status"] != "transcribed":
            raise Problem("transcript_unavailable", "A successful transcript must be reviewed first")
        if not text.strip():
            raise Problem("empty_transcript", "Reviewed text cannot be blank", 422)
        identity = digest({"audio_source_id": audio_id, "reviewed_text": text})
        prior = s.db.audio_reviews.find_one(s.query(request_key=key))
        if prior:
            if prior["identity"] != identity:
                raise Problem("idempotency_conflict", "Review key belongs to different text")
            if prior["status"] != "ready":
                raise Problem("review_pending_or_failed", "Review is pending or failed; reload or explicitly retry with a new key")
            return self.service.public(Source, s.get("sources", "source_id", prior["source_id"]))
        source_id = uid("source")
        try:
            s.db.audio_reviews.insert_one(s.doc(request_key=key, identity=identity, status="processing", source_id=source_id))
        except DuplicateKeyError:
            return self.review(audio_id, text, key)
        try:
            extracted, raw = self.service.provider.propose_from_text(text)
            doc = s.doc(source_id=source_id, source_kind="audio", audio_source_id=audio_id, audio_url=audio["audio_url"],
                sha256=audio["sha256"], mime_type="audio/wav", image_url=None, extracted_text=text,
                quotation=extracted["quotation"], proposed_text=extracted["proposed_text"], proposed_scope=extracted["proposed_scope"],
                trust="untrusted", provenance={"provider": self.store.settings.llm_provider, "model": self.store.settings.agent_model,
                    "transcription_model": audio["model"], "original_transcript": audio["transcript"], "reviewed_text": text,
                    "transcript_corrected": text != audio["transcript"], "reviewed_at": now(), "usage": raw.get("usage")})
            s.db.sources.insert_one(doc)
            s.db.audio_reviews.update_one(s.query(request_key=key), {"$set": {"status": "ready"}})
            return self.service.public(Source, doc)
        except Exception:
            s.db.audio_reviews.update_one(s.query(request_key=key), {"$set": {"status": "failed"}})
            raise Problem("proposal_failed", "Transcript is retained, but proposal extraction failed; explicitly retry after inspection", 502) from None
