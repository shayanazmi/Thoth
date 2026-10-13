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
    API_BASE_URL: str = Field(default="", description="Target gateway URL for web client")

    # Supabase (Auth & Postgres DB)
    SUPABASE_URL: str = Field(default="", description="Supabase project URL")
    SUPABASE_ANON_KEY: str = Field(default="", description="Public Supabase client key")
    SUPABASE_SERVICE_ROLE_KEY: str = Field(default="", description="Supabase server administrative service key")
    SUPABASE_JWT_SECRET: str = Field(default="", description="Supabase JWT secret for token verification")

    # Redis (Caching & Rate Limiting)
    REDIS_URL: str = Field(default="redis://localhost:6379/0", description="Redis connection URI")
    REDIS_CACHE_TTL: int = Field(default=86400, description="Default cache TTL in seconds")

    # Primary LLM Provider (NVIDIA NIM)
    NVIDIA_API_KEY: Optional[str] = Field(default=None, description="NVIDIA NIM API key")
    NVIDIA_PRIMARY_MODEL: str = Field(default="nvidia/nemotron-3.5-lightning-30b-a3b", description="Primary synthesis model")

    # Fallback LLM Provider (Groq)
    GROQ_API_KEY: Optional[str] = Field(default=None, description="Groq API key")
    GROQ_FALLBACK_MODEL: str = Field(default="openai/gpt-oss-120b", description="Fallback research model")
    GROQ_VERIFIER_MODEL: str = Field(default="openai/gpt-oss-20b", description="SLM Truth Guard model")

    # Tertiary Fallback LLM Provider (OpenAI)
    OPENAI_API_KEY: Optional[str] = Field(default=None, description="OpenAI API key")

    # Scholarly & Web Search APIs
    TAVILY_API_KEY: Optional[str] = Field(default=None, description="Tavily search API key")
    SEMANTIC_SCHOLAR_API_KEY: Optional[str] = Field(default=None, description="Semantic Scholar API key")
    HF_TOKEN: Optional[str] = Field(default=None, description="Hugging Face hub token")

    # Telemetry
    DEEPEVAL_TELEMETRY_OPT_OUT: str = Field(default="YES", description="DeepEval telemetry opt out")

    model_config = SettingsConfigDict(
        env_file=os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".env")),
        env_file_encoding="utf-8",
        extra="ignore"
    )

@lru_cache()
def get_settings() -> Settings:
    return Settings()
