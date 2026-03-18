"""
数据库连接模块
"""
import asyncpg
from typing import Optional
from contextlib import asynccontextmanager
from .config import settings


class Database:
    """数据库连接管理"""
    
    def __init__(self):
        self.pool: Optional[asyncpg.Pool] = None
    
    async def connect(self):
        """创建数据库连接池"""
        if self.pool is None:
            self.pool = await asyncpg.create_pool(
                host=settings.DATABASE_HOST,
                port=settings.DATABASE_PORT,
                database=settings.DATABASE_NAME,
                user=settings.DATABASE_USER,
                password=settings.DATABASE_PASSWORD,
                min_size=5,
                max_size=20
            )
    
    async def disconnect(self):
        """关闭数据库连接池"""
        if self.pool:
            await self.pool.close()
            self.pool = None
    
    @asynccontextmanager
    async def get_connection(self):
        """获取数据库连接"""
        if self.pool is None:
            await self.connect()
        
        async with self.pool.acquire() as connection:
            yield connection
    
    async def execute(self, query: str, *args):
        """执行 SQL 语句"""
        async with self.get_connection() as conn:
            return await conn.execute(query, *args)
    
    async def fetch(self, query: str, *args):
        """查询多行数据"""
        async with self.get_connection() as conn:
            return await conn.fetch(query, *args)
    
    async def fetchrow(self, query: str, *args):
        """查询单行数据"""
        async with self.get_connection() as conn:
            return await conn.fetchrow(query, *args)
    
    async def fetchval(self, query: str, *args):
        """查询单个值"""
        async with self.get_connection() as conn:
            return await conn.fetchval(query, *args)


# 全局数据库实例
db = Database()
