from functools import lru_cache

from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    gemini_model: str = "gemini-1.5-pro-002"
    google_cloud_project: str = "glass-record-dev"
    google_genai_use_vertexai: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()


@lru_cache
def get_llm(temperature: float = 0.2) -> ChatGoogleGenerativeAI:
    s = get_settings()
    return ChatGoogleGenerativeAI(
        model=s.gemini_model,
        temperature=temperature,
        project=s.google_cloud_project,
        vertexai=s.google_genai_use_vertexai,
    )
