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

    # ------------------------------------------------------------
    # In-App Purchase validation (Apple / Google).
    # All optional so the app boots without store accounts; endpoints
    # fail with a controlled 503 (validation_unavailable) until set.
    #
    # NOTE: APP_STORE_SHARED_SECRET is intentionally NOT here — it only
    # exists for the deprecated verifyReceipt endpoint. The App Store
    # Server API authenticates with an ES256 JWT built from the three
    # APPLE_* values below.
    # ------------------------------------------------------------
    # TODO(iap): fill in Railway/.env once the Apple Developer account
    # exists — App Store Connect → Users and Access → Integrations →
    # In-App Purchase keys. Download the .p8 once, paste its PEM content
    # into APPLE_PRIVATE_KEY (literal "\n" escapes are supported).
    apple_issuer_id: str | None = None
    apple_key_id: str | None = None
    apple_private_key: str | None = None
    # TODO(iap): fill once the Google Play Console account exists —
    # create a service account with the "View financial data" permission,
    # link it in Play Console → API access. Accepts either the raw JSON
    # string or a filesystem path to the JSON key file.
    google_play_service_account_json: str | None = None
    # Bundle id (iOS) / package name (Android). Same value on both stores.
    app_bundle_id: str = "com.bonvivant.app"

    model_config = SettingsConfigDict(
        env_file=".env", case_sensitive=False, extra="ignore"
    )

    @computed_field
    @property
    def jwks_url(self) -> str:
        return f"{self.supabase_url}/auth/v1/.well-known/jwks.json"


settings = Settings()
