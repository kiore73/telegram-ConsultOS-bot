from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from ..config import settings

async_engine = None
async_session_maker = async_sessionmaker(class_=AsyncSession, expire_on_commit=False)

def init_engine():
    global async_engine
    async_engine = create_async_engine(
        settings.database_url,
        echo=False,
        connect_args={"timeout": 30},
    )
    async_session_maker.configure(bind=async_engine)

async def get_async_session():
    """
    Dependency function that provides an async session.
    """
    async with async_session_maker() as session:
        yield session
