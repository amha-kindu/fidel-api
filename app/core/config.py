from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    env: str = "dev"
    api_v1_prefix: str = "/api/v1"

    database_url: str = "postgresql+asyncpg://postgres:postgres@db:5432/fidel"
    redis_url: str = "redis://localhost:6379/0"

    jwt_secret: str = "changeme"
    jwt_algorithm: str = "HS256"
    access_token_exp_minutes: int = 60 * 24 * 7

    inference_base_url: str = "http://inference:8001"
    inference_timeout_s: float = 60.0

settings = Settings()
