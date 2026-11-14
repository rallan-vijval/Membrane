from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")
    mongodb_uri: SecretStr = SecretStr("")
    mongodb_db: str = "membrane"
    workspace_id: str = "membrane-demo-v1"
    openai_api_key: SecretStr = SecretStr("")
    agent_model: str = ""
    vision_model: str = ""
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = Field(default=1536, ge=1, le=4096)
    model_timeout_seconds: int = Field(default=45, ge=1, le=120)
    max_agent_turns: int = Field(default=3, ge=1, le=3)
    max_run_model_calls: int = Field(default=80, ge=1, le=10000)
    max_concurrent_model_calls: int = Field(default=2, ge=1, le=2)
    model_temperature: float | None = None
    model_max_output_tokens: int = Field(default=1200, ge=100, le=8000)
    worker_enabled: bool = True
    lease_seconds: int = Field(default=180, ge=60)
    data_dir: Path = ROOT / "uploads"
    frontend_origin: str = "http://127.0.0.1:5173"
    voice_enabled: bool = False
    elevenlabs_api_key: SecretStr = SecretStr("")
    elevenlabs_tts_model: str = "eleven_multilingual_v2"
    elevenlabs_voice_id: str = ""
    max_tts_characters_per_request: int = Field(default=2000, ge=1, le=10000)
    max_tts_characters_total: int = Field(default=20000, ge=1)
