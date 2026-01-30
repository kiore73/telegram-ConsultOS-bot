from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from ..config import settings

# Создаем асинхронный движок для взаимодействия с БД
async_engine = create_async_engine(
    settings.database_url,
    echo=False,  # Включаем логирование SQL-запросов, если нужно для отладки
)

# Создаем фабрику сессий для создания асинхронных сессий
async_session_maker = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False
)

async def get_async_session():
    """
    Dependency function that provides an async session.
    """
    async with async_session_maker() as session:
        yield session
