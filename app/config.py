from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DATABASE_URL: str
    JWT_SECRET: str
    JWT_ALGORITHM: str = "HS256"
    HOST_TOKEN_EXPIRE_HOURS: int = 24
    PARTICIPANT_TOKEN_EXPIRE_HOURS: int = 24
    SUBMIT_ANSWER_COOLDOWN_SECONDS: float = 2.0


def load_settings() -> Settings:
    try:
        return Settings()
    except Exception as exc:
        raise RuntimeError(
            "Missing required environment variables (DATABASE_URL, JWT_SECRET). "
            "Copy .env.example to .env and fill in values."
        ) from exc


settings = load_settings()
