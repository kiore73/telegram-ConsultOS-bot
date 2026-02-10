from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from bot.config import settings
from .models import Base


def create_db_engine():
    """
    Creates and returns a new SQLAlchemy async engine.
    """
    return create_async_engine(
        settings.database_url,
        echo=False,
        connect_args={"timeout": 30},
    )

def create_session_maker(engine) -> async_sessionmaker[AsyncSession]:
    """
    Creates and returns a fully configured SQLAlchemy async session maker.
    """
    return async_sessionmaker(
        bind=engine, class_=AsyncSession, expire_on_commit=False
    )
