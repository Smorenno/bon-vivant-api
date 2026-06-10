from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    supabase_url: str
    supabase_service_role_key: str
    jwt_secret: str
    debug: bool = False
    mapbox_token: str | None = None  # Optional; NullGeocoder used when absent

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False)


settings = Settings()
