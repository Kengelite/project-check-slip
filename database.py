from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base

# ชี้ไปที่ PostgreSQL ที่เรารันไว้ใน Docker เมื่อกี้
DATABASE_URL = "postgresql+asyncpg://admin:supersecretpassword@localhost:5432/slip_db"

engine = create_async_engine(DATABASE_URL, echo=False)

AsyncSessionLocal = sessionmaker(
    bind=engine, class_=AsyncSession, expire_on_commit=False
)

Base = declarative_base()

# ฟังก์ชันสำหรับให้ FastAPI ดึงท่อเชื่อมต่อ Database ไปใช้
async def get_db():
    async with AsyncSessionLocal() as session:
        yield session