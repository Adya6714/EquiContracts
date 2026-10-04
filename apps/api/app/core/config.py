"""Environment-backed application settings."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = (
        "postgresql+psycopg://equicontracts_app:localdev@localhost:5432/equicontracts"
    )
    admin_database_url: str = (
        "postgresql+psycopg://postgres:localdev@localhost:5432/equicontracts"
    )
    system_database_url: str = (
        "postgresql+psycopg://equicontracts_system:localdev"
        "@localhost:5432/equicontracts"
    )
    agent_database_url: str = (
        "postgresql+psycopg://equicontracts_agent:localdev@localhost:5432/equicontracts"
    )
    s3_endpoint_url: str = "http://localhost:9000"
    s3_bucket: str = "equicontracts-documents"
    s3_access_key: str = "minioadmin"
    s3_secret_key: str = "minioadmin"
    inbound_email_hmac_secret: str = "change-me-in-production"
    # Shared mailbox local-part; projects are routed via projects+{alias}@domain.
    inbound_mailbox: str = "projects"
    inbound_email_domain: str = "equicontracts.local"
    auth_mode: str = "dev_header"


@lru_cache
def get_settings() -> Settings:
    return Settings()
