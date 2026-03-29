"""
数据库连接模块

v5.0 简化架构：使用 container_tag 隔离用户数据，无需 schema 隔离
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
                max_size=20,
            )

            await self._register_vector_codec()

    async def _register_vector_codec(self):
        """注册向量类型编码器（暂时跳过）"""
        pass

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

    async def execute(self, query: str, *args, conn=None):
        """执行 SQL 语句"""
        if conn:
            return await conn.execute(query, *args)

        async with self.get_connection() as conn:
            return await conn.execute(query, *args)

    async def fetch(self, query: str, *args, conn=None):
        """查询多行数据"""
        if conn:
            return await conn.fetch(query, *args)

        async with self.get_connection() as conn:
            return await conn.fetch(query, *args)

    async def fetchrow(self, query: str, *args, conn=None):
        """查询单行数据"""
        if conn:
            return await conn.fetchrow(query, *args)

        async with self.get_connection() as conn:
            return await conn.fetchrow(query, *args)

    async def fetchval(self, query: str, *args, conn=None):
        """查询单个值"""
        if conn:
            return await conn.fetchval(query, *args)

        async with self.get_connection() as conn:
            return await conn.fetchval(query, *args)

    @asynccontextmanager
    async def transaction(self):
        """事务上下文管理器"""
        async with self.get_connection() as conn:
            async with conn.transaction():
                yield conn


db = Database()
