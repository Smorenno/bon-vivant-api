from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    supabase_url: str
    supabase_service_role_key: str
    # Optional: only needed for HS256 legacy tokens issued before Supabase
    # migrated the project to asymmetric ES256 keys. Absence does not break
    # startup; it only means legacy HS256 tokens will be rejected.
    jwt_secret: str | None = None
    debug: bool = False
    mapbox_token: str | None = None
    jwt_audience: str = "authenticated"
    jwt_leeway_seconds: int = 10

    model_config = SettingsConfigDict(
        env_file=".env", case_sensitive=False, extra="ignore"
    )

    @computed_field
    @property
    def jwks_url(self) -> str:
        return f"{self.supabase_url}/auth/v1/.well-known/jwks.json"


settings = Settings()
