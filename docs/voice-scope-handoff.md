# Voice sources and scope experiments: integration handoff

Branch: `feat/memory-experiments-voice-sources`, based on main `51b5583`. This is a functional integration, not the team's visual redesign. Main has not been merged with this feature branch.

## What is implemented

- Audio upload or browser microphone recording -> ElevenLabs Scribe v2 batch transcription -> explicit transcript review -> DeepSeek text proposal -> existing candidate/admission flow. No image-rendering workaround for transcripts.
- Seven policy-authored boundary scenarios from the order-4821 development anchor. Two sides, two repetitions: 28 initial decisions, at most 56 attempted generation requests. Proposal context is intentionally added even outside its claimed scope and is labeled a stress test, not production retrieval.
- Immutable scenario facts, exception snapshots, retrieval, profile/model configuration, hashes, raw responses, checks and usage. Expired-exception tests modify a copy only. Worker uses leases, persisted results, call reservation and recovery; interrupted preparation fails without automatic paid retry.
- Scope experiments have their own collections and `admission_evidence=false`. They never update candidate status, latest admission run, trusted exceptions or active memory. A completed experiment can still contain violations or inconclusive evidence.

## Setup for voice sources

The existing Atlas, DeepSeek and Voyage setup remains in use. Add the ElevenLabs key to the ignored `.env` and set:

```dotenv
ELEVENLABS_API_KEY=your_key_with_speech_to_text_permission
TRANSCRIPTION_ENABLED=true
TRANSCRIPTION_MODEL=scribe_v2
```

Restart FastAPI after changing configuration. No ElevenLabs voice ID is needed for transcription. `VOICE_ENABLED` remains independent and controls the older answer-playback feature only. No OpenAI key is required for the default providers.

Install ffmpeg and ffprobe on PATH; alternatively set `FFMPEG_PATH` and `FFPROBE_PATH` to their executable paths. Both are present on the current Windows machine. Server-side probing validates actual container/audio content and duration; uploaded names and browser metadata are not trusted. Browser recordings without WebM duration are measured after bounded decoding.

Limits: audio-only MP3/WAV/M4A/OGG/WebM, 0.1-120 seconds, at most 10 MiB, normalized mono 16 kHz PCM for transcription. One transcription per backend process at a time. The workspace reserves at most 600 submitted seconds across requests, including failed provider attempts. This is a local usage cap, not an estimate of account credits. Provider timeout is 90 seconds; there are no automatic speech retries. Explicit new attempts consume budget. Health reports transcription configuration independently and makes no paid call.

Original audio and normalized playback remain under the ignored uploads directory. Atlas holds transcript/provenance and request states. Original transcripts and word times are immutable; reviewed text is a separate source revision. Word navigation refers to original speech, even after text corrections. Audio remains untrusted and cannot create authenticated business exceptions.

## Public APIs

The complete schemas and generated TypeScript are in the existing contract files. `contracts/examples.json` includes clearly synthetic audio and experiment examples.

| Endpoint | Behavior |
| --- | --- |
| POST /api/audio-sources | Multipart `file`; required Idempotency-Key; returns AudioSource. Provider failures are persisted as `status=failed`, with a safe error code. |
| GET /api/audio-sources/{id} | Reload state/original transcript/timestamps; no new transcription. |
| GET /api/audio-sources/{id}/audio | Workspace-scoped normalized WAV playback. |
| POST /api/audio-sources/{id}/review | `{reviewed_text}` plus Idempotency-Key; returns a Source proposal. No staging or approval. |
| POST /api/candidates/{id}/experiments/scope | `{base_version_id}` plus Idempotency-Key; returns experiment_id. Same key/request reuses the job; changed payload conflicts. |
| GET /api/experiments/{id} | Progress, frozen scenarios, paired raw evidence, consistency, actual classifications and usage. |

Source adds `source_kind`, `audio_source_id`, `audio_url` and nullable `image_url`. Existing image responses remain valid and default to image kind. Health adds optional transcription status. Existing approval endpoints and benchmark remain unchanged.

## Visual-team integration

Feature modules are isolated in `frontend/src/features/memory-lab/`. No CSS was changed on this branch. Reskin these components or use their typed API helper with your template:

- VoiceSourceIntake accepts `onSourceReady(source)` and `disabled`. It provides file selection, recording stop/cancel, playback, transcription state and explicit transcript confirmation. A small hook in the existing SourcePanel mounts it; a reviewed source resets the current proposal/run through App.
- ScopeExperimentPanel accepts candidate, baseVersionId and disabled. It displays real progress, changed facts, trusted policy, expected behavior, actual actions and raw evidence. Its small App hook sits beside the existing experiment controls; move it freely without rewriting gating.
- Source view types/adapters carry optional audio URL/kind; render an audio player when image_url is null. Header distinguishes answer audio from transcription.
- URL parameters `audio_source` and `experiment` reload stored evidence; reload never starts another paid job. Original review workspace URL behavior remains.
- Synthetic UI mode disables live voice/microscope submission. Browser tests explicitly intercept only backend HTTP routes; PDF.js/recording controls still run in Chrome.

## Verification

- 113 backend tests passed; two opt-in live tests skipped.
- Production TypeScript/Vite build passed; 19 browser tests passed against local running servers using a temporary no-server Playwright config. The committed config still starts its own servers when ports are free.
- Real DeepSeek/Atlas scope experiment `experiment_5e68eba8214346a1baf6b31f70252911` recorded all 28 decisions with 28 generation calls. Overall status was inconclusive; actual cases included unchanged-safe, baseline violations and a new violation for excess amount. No passing result is fabricated.
- Candidate admission and active version remained unchanged during that live experiment.
- ElevenLabs live transcription passed after credentials were supplied: a 13.7025-second locally synthesized note was transcribed through the application API using scribe_v2 (audio_source_4bbc0b70abd24f41a44d01ecf6f4c199). No candidate was created or activated. Failure paths and transcript review use explicit fakes; ffmpeg WAV and nonseekable WebM decoding were exercised for real.

## Live checks after credentials arrive

Use only synthetic notes. Open the app, expand 'Use a voice note instead', upload or record a clip, transcribe, verify identifiers, correct the text if needed, and explicitly confirm it. Confirm a proposal appears but is not automatically saved or approved. Save it for testing and optionally explore its scope. An uploaded/recorded instruction is not proof of trusted authority.

```powershell
# Requires the backend to be running; sends one explicit transcription request:
.\.venv\Scripts\python.exe -m scripts.lab_smoke --audio path\to\synthetic-note.wav
# Start one paid 28-decision experiment:
.\.venv\Scripts\python.exe -m scripts.lab_smoke --candidate-id CANDIDATE_ID
# Reload/inspect a prior experiment without generating another:
.\.venv\Scripts\python.exe -m scripts.lab_smoke --experiment-id EXPERIMENT_ID
```

The CLI leaves transcript confirmation manual and never approves memory. Its successful exit for a finished experiment means the pipeline and isolation checks passed, not that the candidate is safe. New collections/indexes are created lazily by the feature routes; existing workspace state receives only the transcription usage counter. Unrelated records and trusted exceptions are preserved.
