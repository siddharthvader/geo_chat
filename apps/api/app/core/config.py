from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql://postgres:postgres@localhost:5432/buildingtalk"
    llm_provider: str = "openai"
    llm_model: str = "gpt-4.1-mini"
    embed_model: str = "text-embedding-3-large"
    openai_api_key: str = ""
    openai_base_url: str = ""
    openrouter_api_key: str = ""
    top_k: int = 8
    max_context_chars: int = 18000
    embed_dim: int = 3072
    buildings_file: str = "data/buildings/buildings.json"
    hotspots_file: str = "data/hotspots/palace_hotspots.json"
    processed_dir: str = "data/processed"
    allow_keyword_fallback: bool = True

    @property
    def resolved_buildings_path(self) -> Path:
        return (Path(__file__).resolve().parents[4] / self.buildings_file).resolve()

    @property
    def resolved_hotspots_path(self) -> Path:
        return (Path(__file__).resolve().parents[4] / self.hotspots_file).resolve()

    @property
    def resolved_processed_dir(self) -> Path:
        return (Path(__file__).resolve().parents[4] / self.processed_dir).resolve()


@lru_cache
def get_settings() -> Settings:
    return Settings()
