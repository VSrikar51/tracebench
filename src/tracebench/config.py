"""Settings for tracebench, read from the .env file."""

from datetime import date

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    store_today: date = date(2026, 10, 1)


settings = Settings()