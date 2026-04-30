from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    DATABASE_URL: str
    SIPRI_BASE_URL: str = "https://sipri.juntadeandalucia.es"
    NOMINATIM_BASE_URL: str = "https://nominatim.openstreetmap.org"
    OSRM_BASE_URL: str = "https://router.project-osrm.org"
    USER_AGENT: str = "InterinosBot/1.0"
    CORS_ORIGIN: str = "http://localhost:5173"
    ADMIN_TOKEN: str = "change-me"
    LOG_LEVEL: str = "INFO"
    SCRAPE_CRON: str = "0 */6 * * *"

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGIN.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
