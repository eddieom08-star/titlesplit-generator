from pydantic_settings import BaseSettings
from pydantic import field_validator
from functools import lru_cache


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql+asyncpg://postgres:password@localhost:5432/titlesplit"
    database_url_sync: str = "postgresql://postgres:password@localhost:5432/titlesplit"

    @field_validator("database_url", mode="before")
    @classmethod
    def convert_database_url(cls, v: str) -> str:
        """Convert Render's postgres:// to asyncpg format."""
        if v.startswith("postgres://"):
            return v.replace("postgres://", "postgresql+asyncpg://", 1)
        if v.startswith("postgresql://") and "+asyncpg" not in v:
            return v.replace("postgresql://", "postgresql+asyncpg://", 1)
        return v

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # API Keys
    anthropic_api_key: str = ""
    property_data_api_key: str = ""

    # App Settings
    debug: bool = False
    log_level: str = "INFO"

    # Scraping Settings
    scrape_interval_hours: int = 6
    max_concurrent_scrapes: int = 5

    # Analysis Thresholds
    min_units_for_opportunity: int = 2
    min_gross_uplift_percent: float = 15.0
    min_net_benefit_per_unit: int = 2000

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache
def get_settings() -> Settings:
    return Settings()
