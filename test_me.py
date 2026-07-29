import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select
from db.indian_models import User
import sys
import os
sys.path.append(os.path.join(os.getcwd(), 'backend'))

async def main():
    engine = create_async_engine("postgresql+asyncpg://trader:trader_pass@localhost:5432/trading_system")
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        result = await session.execute(select(User).where(User.email == 'itzmesomil@gmail.com'))
        user = result.scalar_one_or_none()
        print(f"User email: {user.email}")
        print(f"User name: {user.name}")
        print(f"Type of name: {type(user.name)}")

if __name__ == "__main__":
    asyncio.run(main())
