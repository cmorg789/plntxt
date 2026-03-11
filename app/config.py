from pydantic import computed_field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    POSTGRES_USER: str = "plntxt"
    POSTGRES_PASSWORD: str = "plntxt"
    POSTGRES_SERVER: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "plntxt"

    SECRET_KEY: str = "change-me"
    AGENT_API_KEY: str = "change-me"

    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 1 week

    ANTHROPIC_API_KEY: str = ""
    APP_BASE_URL: str = "http://localhost:8000"

    # Email (SMTP)
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = "noreply@plntxt.blog"
    SMTP_USE_TLS: bool = True
    VERIFICATION_TOKEN_EXPIRE_HOURS: int = 48

    @computed_field
    @property
    def DATABASE_URL(self) -> str:
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:"
            f"{self.POSTGRES_PASSWORD}@{self.POSTGRES_SERVER}:"
            f"{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
