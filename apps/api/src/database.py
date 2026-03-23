"""
数据库连接模块
"""
import asyncpg
from typing import Optional, List
from contextlib import asynccontextmanager
from contextvars import ContextVar
from .config import settings

# 使用 contextvar 存储当前请求的 user_id
_current_user_id: ContextVar[Optional[str]] = ContextVar('current_user_id', default=None)


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
            
            # 注册向量类型编码器
            await self._register_vector_codec()
    
    async def _register_vector_codec(self):
        """注册向量类型编码器（暂时跳过）"""
        print("⚠️ 跳过向量编码器注册，使用字符串格式存储")
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
            # 自动设置用户 schema
            user_id = _current_user_id.get()
            if user_id:
                await conn.execute("SELECT set_user_schema($1)", user_id)
            return await conn.execute(query, *args)
    
    async def fetch(self, query: str, *args, conn=None):
        """查询多行数据"""
        if conn:
            return await conn.fetch(query, *args)
        
        async with self.get_connection() as conn:
            # 自动设置用户 schema
            user_id = _current_user_id.get()
            if user_id:
                await conn.execute("SELECT set_user_schema($1)", user_id)
            return await conn.fetch(query, *args)
    
    async def fetchrow(self, query: str, *args, conn=None):
        """查询单行数据"""
        if conn:
            return await conn.fetchrow(query, *args)
        
        async with self.get_connection() as conn:
            # 自动设置用户 schema
            user_id = _current_user_id.get()
            if user_id:
                await conn.execute("SELECT set_user_schema($1)", user_id)
            return await conn.fetchrow(query, *args)
    
    async def fetchval(self, query: str, *args, conn=None):
        """查询单个值"""
        if conn:
            return await conn.fetchval(query, *args)
        
        async with self.get_connection() as conn:
            # 自动设置用户 schema
            user_id = _current_user_id.get()
            if user_id:
                await conn.execute("SELECT set_user_schema($1)", user_id)
            return await conn.fetchval(query, *args)
    
    @asynccontextmanager
    async def transaction(self, user_id: str = None):
        """
        事务上下文管理器，支持用户 schema 隔离
        
        Args:
            user_id: 用户 ID（可选，如果提供则自动切换到用户 schema）
        
        Usage:
            async with db.transaction(user_id="test") as conn:
                # 在这里所有数据库操作都在 test 用户的 schema 下
                await db.execute("INSERT INTO memories ...", conn=conn)
        """
        async with self.get_connection() as conn:
            async with conn.transaction():
                if user_id:
                    # 切换到用户 schema
                    await conn.execute("SELECT set_user_schema($1)", user_id)
                yield conn
    
    async def set_user_schema(self, user_id: str) -> str:
        """
        切换到用户的 schema
        
        Args:
            user_id: 用户 ID
        
        Returns:
            schema 名称
        
        Raises:
            Exception: 如果用户不存在
        """
        # 调用数据库函数切换 schema
        schema_name = await self.fetchval(
            "SELECT set_user_schema($1)",
            user_id
        )
        return schema_name
    
    async def init_user(self, user_id: str) -> dict:
        """
        初始化用户（创建用户 schema）
        
        Args:
            user_id: 用户 ID
        
        Returns:
            用户信息 {user_id, schema_name}
        
        Raises:
            Exception: 如果用户已存在或创建失败
        """
        # 检查用户是否已存在
        existing = await self.fetchrow(
            "SELECT id, schema_name FROM users WHERE id = $1",
            user_id
        )
        
        if existing:
            return {
                "user_id": existing["id"],
                "schema_name": existing["schema_name"],
                "already_exists": True
            }
        
        # 创建用户 schema（如果不存在则自动创建）
        await self.execute(f"SELECT get_or_create_user_schema('{user_id}')")
        
        # 获取用户信息
        user = await self.fetchrow(
            "SELECT id, schema_name FROM users WHERE id = $1",
            user_id
        )
        
        return {
            "user_id": user["id"],
            "schema_name": user["schema_name"],
            "already_exists": False
        }
    
    @asynccontextmanager
    async def user_context(self, user_id: str = "develop"):
        """
        用户上下文管理器：自动切换 schema 并在完成后恢复
        
        Args:
            user_id: 用户 ID（默认 develop）
        
        Usage:
            async with db.user_context("test"):
                # 在这里所有数据库操作都在 test 用户的 schema 下
                await db.execute("INSERT INTO memories ...")
        """
        # 设置当前 user_id
        token = _current_user_id.set(user_id)
        
        try:
            yield
        finally:
            # 恢复原来的值
            _current_user_id.reset(token)
    
    def set_current_user(self, user_id: str):
        """
        设置当前请求的用户 ID
        
        Args:
            user_id: 用户 ID
        
        Usage:
            db.set_current_user("test")
            # 后续的数据库操作会自动使用 test 用户的 schema
        """
        _current_user_id.set(user_id)


# 全局数据库实例
db = Database()
