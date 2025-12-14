from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # Database
    DATABASE_URL: str

    # JWT
    SECRET_KEY: str
    ALGORITHM: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int

    # Stripe
    STRIPE_SECRET_KEY: str
    STRIPE_PUBLISHABLE_KEY: str
    STRIPE_WEBHOOK_SECRET: str

    # Email
    MAIL_USERNAME: str | None = None
    MAIL_PASSWORD: str | None = None
    MAIL_FROM: str | None = None
    MAIL_PORT: int | None = None
    MAIL_SERVER: str | None = None
    MAIL_FROM_NAME: str | None = None

    # App Config
    APP_NAME: str
    APP_URL: str
    FRONTEND_URL: str

    # AEMET
    AEMET_API_KEY: str

    # Plans
    PLAN_FREE_QUERIES: int
    PLAN_PRO_QUERIES: int
    PLAN_PRO_PRICE: float
    PLAN_ENTERPRISE_PRICE: float

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()

