from pydantic_settings import BaseSettings, SettingsConfigDict


class Config(BaseSettings):
    BOT_TOKEN: str

    POSTGRES_HOST: str = "postgres"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "wishbook"
    POSTGRES_USER: str = "wishbook"
    POSTGRES_PASSWORD: str = "changeme"

    REDIS_URL: str = "redis://redis:6379/0"
    NOTIFICATION_DELAY_SECONDS: int = 300  # 5 minutes; change freely in .env

    # Fernet symmetric key — generate with:
    # python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    ENCRYPTION_KEY: str

    @property
    def postgres_dsn(self) -> str:
        return (
            f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


config = Config()
