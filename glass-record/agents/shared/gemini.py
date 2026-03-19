from functools import lru_cache

from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    gemini_model: str = "gemini-3.1-pro-preview"
    gemini_fallback_model: str = "gemini-3.0-flash-preview"
    google_cloud_project: str = "glass-record-dev"
    google_genai_use_vertexai: bool = True
    monthly_budget_usd: float = 50.0  # global default; override per-journalist via JournalistConfig
    gcs_evidence_bucket: str = "glass-record-evidence-prod"


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


def get_llm_with_fallback(temperature: float = 0.2):
    """
    Primary LLM with automatic fallback to the flash model on quota exhaustion
    or sustained service unavailability.

    Use this for raw ainvoke() call sites. For structured-output callers
    (with_structured_output), use get_llm() directly.
    """
    from google.api_core.exceptions import ResourceExhausted, ServiceUnavailable

    s = get_settings()
    primary = ChatGoogleGenerativeAI(
        model=s.gemini_model,
        temperature=temperature,
        project=s.google_cloud_project,
        vertexai=s.google_genai_use_vertexai,
    )
    fallback = ChatGoogleGenerativeAI(
        model=s.gemini_fallback_model,
        temperature=temperature,
        project=s.google_cloud_project,
        vertexai=s.google_genai_use_vertexai,
    )
    return primary.with_fallbacks(
        [fallback],
        exceptions_to_handle=(ResourceExhausted, ServiceUnavailable),
    )
