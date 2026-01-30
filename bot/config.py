from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import SecretStr, Field
from typing import List

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8')

    # Telegram Bot Token
    BOT_TOKEN: SecretStr

    # Telegram User IDs of admins
    ADMIN_IDS: List[int] = Field(default_factory=list, env='ADMIN_IDS', sa_alias='ADMIN_IDS', sa_type=str,
                                  description='Comma-separated list of Telegram user IDs who are admins')

    # YKassa Token
    YUKASSA_TOKEN: SecretStr | None = None # Make it optional

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
