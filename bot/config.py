from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import SecretStr, Field
from typing import List

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8')

    # Telegram Bot Token
    BOT_TOKEN: SecretStr

    # Telegram User IDs of admins
    ADMIN_IDS: List[int] = Field(default_factory=list)

    # --- YooKassa Settings ---
    # Token for native Telegram Payments API (legacy)
    YUKASSA_PAYMENTS_TOKEN: SecretStr | None = None

    # Settings for direct YooKassa API integration
    YOOKASSA_ENABLED: bool = False
    YOOKASSA_SHOP_ID: SecretStr | None = None
    YOOKASSA_SECRET_KEY: SecretStr | None = None
    YOOKASSA_RETURN_URL: str | None = None
    YOOKASSA_DEFAULT_RECEIPT_EMAIL: str | None = None
    YOOKASSA_VAT_CODE: int = 1  # 1 = "Без НДС"
    YOOKASSA_PAYMENT_MODE: str = "full_prepayment"
    YOOKASSA_PAYMENT_SUBJECT: str = "service"

    # --- Service Price ---
    SERVICE_PRICE: float = 1000.00

    # --- Webhook Settings ---
    WEBHOOK_HOST: str | None = None # e.g. https://your-domain.com
    WEBHOOK_PATH: str = "/webhook/bot"
    WEB_SERVER_HOST: str = "0.0.0.0"
    WEB_SERVER_PORT: int = 8080

    # Database settings
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_DB: str
    POSTGRES_HOST: str = 'db'
    POSTGRES_PORT: int = 5432

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

# Create a single instance of the settings
settings = Settings()
