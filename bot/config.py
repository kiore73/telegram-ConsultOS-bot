from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import SecretStr
from typing import List
import logging

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8')

    # Telegram Bot Token
    BOT_TOKEN: SecretStr

    # Telegram User IDs of admins (as a string)
    ADMIN_IDS: str = ""

    # --- YooKassa Settings ---

    YOOKASSA_ENABLED: bool = False
    YOOKASSA_SHOP_ID: SecretStr | None = None
    YOOKASSA_SECRET_KEY: SecretStr | None = None
    YOOKASSA_RETURN_URL: str | None = None # For user redirection after payment
    YOOKASSA_NOTIFICATION_URL: str | None = None # For server-to-server payment status notifications
    YOOKASSA_DEFAULT_RECEIPT_EMAIL: str | None = None
    YOOKASSA_VAT_CODE: int = 1
    YOOKASSA_PAYMENT_MODE: str = "full_prepayment"
    YOOKASSA_PAYMENT_SUBJECT: str = "service"

    # --- Service Price ---
    SERVICE_PRICE: float = 1000.00

    # --- Webhook Settings ---
    WEBHOOK_HOST: str | None = None
    WEBHOOK_PATH: str = "/webhook/bot"
    WEB_SERVER_HOST: str = "0.0.0.0"
    WEB_SERVER_PORT: int = 8080

    # --- Database settings ---
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_DB: str
    POSTGRES_HOST: str = 'db'
    POSTGRES_PORT: int = 5432

    @property
    def admin_ids_list(self) -> List[int]:
        """ Parses the ADMIN_IDS string into a list of integers. """
        if not self.ADMIN_IDS:
            return []
        try:
            return [int(admin_id.strip()) for admin_id in self.ADMIN_IDS.split(',')]
        except ValueError:
            logging.error("Could not parse ADMIN_IDS. Please ensure it's a comma-separated list of numbers.")
            return []

    @property
    def database_url(self) -> str:
        """ Correctly constructs the database URL. """
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

# Create a single instance of the settings
settings = Settings()

