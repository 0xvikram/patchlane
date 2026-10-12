import tomllib
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

Role = Literal["orchestrator", "coder", "light"]

REPO_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    llm_base_url: str = ""
    llm_api_key: str = Field(default="", validation_alias=AliasChoices("LLM_API_KEY", "BEDROCK_API_KEY"))
    neatlogs_api_key: str = ""


class LLMConfig(BaseModel):
    models: dict[Role, str] = {}
    timeout_seconds: float = 60
    max_output_tokens: int = 1024


class Config(BaseModel):
    llm: LLMConfig = LLMConfig()


def load_config(path: Path | None = None) -> Config:
    path = path or REPO_ROOT / "config.toml"
    if not path.exists():
        return Config()
    return Config.model_validate(tomllib.loads(path.read_text()))


@lru_cache
def get_settings() -> Settings:
    return Settings()
