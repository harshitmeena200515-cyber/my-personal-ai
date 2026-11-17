from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


class Settings(BaseSettings):
    PROJECT_NAME: str = "MY PERSONAL AI"
    VERSION: str = "0.1.0"
    HOST: str = "127.0.0.1"
    PORT: int = 8000
    DEBUG: bool = True
    ENVIRONMENT: str = "development"

    # Router Settings
    DEFAULT_LOCAL_MODEL: str = "qwen2.5-coder:3b"
    DEFAULT_CLOUD_MODEL: str = "gemini-2.0-flash"
    ROUTER_MODE: str = "hybrid"  # local_only, hybrid, cloud_only

    # Local Engine URLs
    OLLAMA_BASE_URL: str = "http://localhost:11434"

    # Cloud Provider Keys
    GEMINI_API_KEY: Optional[str] = None
    GROQ_API_KEY: Optional[str] = None
    OPENAI_API_KEY: Optional[str] = None
    ANTHROPIC_API_KEY: Optional[str] = None

    # Paths
    APP_DB_PATH: str = "./data/app.db"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
