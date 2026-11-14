from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")
    mongodb_uri: SecretStr = SecretStr("")
    mongodb_db: str = "membrane"
    workspace_id: str = "membrane-demo-v1"
    openai_api_key: SecretStr = SecretStr("")
    deepseek_api_key: SecretStr = SecretStr("")
    llm_provider: Literal["openai", "deepseek"] = "deepseek"
    vision_provider: Literal["openai", "deepseek"] = "deepseek"
    deepseek_base_url: str = "https://api.deepseek.com"
    agent_model: str = "deepseek-flash"
    vision_model: str = "deepseek-flash"
    embedding_provider: Literal["openai", "voyage"] = "openai"
    voyage_api_key: SecretStr = SecretStr("")
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
    governed_memory_enabled: bool = False
    langsmith_tracing: bool = False
    langsmith_api_key: SecretStr = SecretStr("")
    gmail_enabled: bool = False
    gmail_client_id: str = ""
    gmail_client_secret: SecretStr = SecretStr("")
    gmail_refresh_token: SecretStr = SecretStr("")
    gmail_max_email_chars: int = Field(default=12000, ge=500, le=50000)

    @property
    def fixture_collection(self):
        return "task_fixtures_v2" if self.governed_memory_enabled else "task_fixtures"

    @property
    def fixture_index(self):
        return "fixture_semantic_v2" if self.governed_memory_enabled else "fixture_semantic_v1"
