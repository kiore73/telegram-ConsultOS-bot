from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from ..config import settings

async def create_session_maker() -> async_sessionmaker[AsyncSession]:
    """
    Creates and returns a fully configured SQLAlchemy async session maker.
    """
    engine = create_async_engine(
        settings.database_url,
        echo=False,
        connect_args={"timeout": 30},
    )
    
    session_maker = async_sessionmaker(
        bind=engine, class_=AsyncSession, expire_on_commit=False
    )
    
    return session_maker


