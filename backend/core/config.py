# Thoth · Developed by Shayan Azmi
import os
from functools import lru_cache
from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # Application & Server
    ENVIRONMENT: str = Field(default="development", description="Runtime environment")
    PORT: int = Field(default=8000, description="Server port")
    HOST: str = Field(default="0.0.0.0", description="Server host")
    LOG_LEVEL: str = Field(default="INFO", description="Logging level")

    # Primary LLM Provider (NVIDIA NIM)
    NVIDIA_API_KEY: Optional[str] = Field(default=None, description="NVIDIA NIM API key")
    NVIDIA_PRIMARY_MODEL: str = Field(default="nvidia/nemotron-3.5-lightning-30b-a3b", description="Primary synthesis model")

    # Fallback LLM Provider (Groq)
    GROQ_API_KEY: Optional[str] = Field(default=None, description="Groq API key")
    GROQ_FALLBACK_MODEL: str = Field(default="openai/gpt-oss-120b", description="Fallback research model")
    GROQ_VERIFIER_MODEL: str = Field(default="openai/gpt-oss-20b", description="Fallback model for short, structured calls")

    # Tertiary Fallback LLM Provider (OpenAI)
    OPENAI_API_KEY: Optional[str] = Field(default=None, description="OpenAI API key")

    # Scholarly & Web Search APIs
    SEMANTIC_SCHOLAR_API_KEY: Optional[str] = Field(default=None, description="Semantic Scholar API key")
    OPENALEX_API_KEY: Optional[str] = Field(default=None, description="OpenAlex API key (cursor paging, own daily budget)")

    model_config = SettingsConfigDict(
        env_file=os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".env")),
        env_file_encoding="utf-8",
        extra="ignore"
    )

@lru_cache()
def get_settings() -> Settings:
    return Settings()
