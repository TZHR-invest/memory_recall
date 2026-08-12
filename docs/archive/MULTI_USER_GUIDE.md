# 多用户 Schema 隔离使用指南

## 概述

Memory Recall 系统已支持多用户数据隔离，每个用户拥有独立的数据库 schema，确保数据安全和隐私保护。

## 架构设计

### Schema 隔离方案

```
PostgreSQL 数据库
├── public schema
│   └── users 表（用户注册表）
├── user_develop schema
│   ├── memories 表
│   ├── entities 表
│   ├── relations 表
│   └── memory_entities 表
└── user_test schema
    ├── memories 表
    ├── entities 表
    ├── relations 表
    └── memory_entities 表
```

### 核心组件

1. **用户注册表** (`public.users`)
   - 记录所有已创建的用户
   - 字段：id, schema_name, created_at, last_active_at

2. **Schema 管理函数**
   - `create_user_schema(user_id)` - 创建用户 schema
   - `set_user_schema(user_id)` - 切换到用户 schema
   - `delete_user_schema(user_id)` - 删除用户 schema
   - `get_or_create_user_schema(user_id)` - 获取或创建用户 schema

## 使用方法

### 1. 初始化用户

**API 端点**: `POST /api/v1/users/init`

**请求示例**:
```bash
curl -X POST "http://localhost:8000/api/v1/users/init" \
  -H "Content-Type: application/json" \
  -d '{"user_id": "my_user"}'
```

**响应示例**:
```json
{
  "code": 200,
  "message": "用户初始化成功",
  "data": {
    "user_id": "my_user",
    "schema_name": "user_my_user",
    "already_exists": false
  }
}
```

### 2. 创建记忆

**API 端点**: `POST /api/v1/memories?user_id=develop`

**请求示例**:
```bash
curl -X POST "http://localhost:8000/api/v1/memories?user_id=develop" \
  -H "Content-Type: application/json" \
  -d '{
    "content": "今天和老同学在咖啡店见面聊天",
    "input_type": "text"
  }'
```

**响应示例**:
```json
{
  "code": 200,
  "message": "success",
  "data": {
    "id": "mem_abc123def456",
    "content": "今天和老同学在咖啡店见面聊天",
    "input_type": "text",
    "created_at": "2024-01-01T12:00:00"
  }
}
```

### 3. 查询记忆

**API 端点**: `GET /api/v1/memories?user_id=develop`

**请求示例**:
```bash
curl -X GET "http://localhost:8000/api/v1/memories?user_id=develop&limit=10"
```

### 4. 搜索记忆

**API 端点**: `POST /api/v1/memories/search?user_id=develop`

**请求示例**:
```bash
curl -X POST "http://localhost:8000/api/v1/memories/search?user_id=develop" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "咖啡店",
    "limit": 10,
    "min_similarity": 0.15
  }'
```

### 5. 自然语言召回

**API 端点**: `POST /api/v1/memories/recall?user_id=develop`

**请求示例**:
```bash
curl -X POST "http://localhost:8000/api/v1/memories/recall?user_id=develop" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "最近在咖啡店发生了什么",
    "limit": 10,
    "use_parser": true,
    "min_similarity": 0.05,
    "detail_level": "medium"
  }'
```

## API 参数说明

### user_id 参数

所有记忆相关的 API 都支持 `user_id` 参数：

- **默认值**: `develop`
- **格式**: 只能包含小写字母、数字和下划线
- **长度**: 1-100 个字符

### 支持的 API

以下 API 都支持 `user_id` 参数：

| API | 端点 | 说明 |
|-----|------|------|
| 创建记忆 | POST /api/v1/memories | 在指定用户的 schema 中创建记忆 |
| 列出记忆 | GET /api/v1/memories | 获取指定用户的记忆列表 |
| 获取记忆 | GET /api/v1/memories/{id} | 获取指定用户的单个记忆 |
| 更新记忆 | PUT /api/v1/memories/{id} | 更新指定用户的记忆 |
| 删除记忆 | DELETE /api/v1/memories/{id} | 删除指定用户的记忆 |
| 语义搜索 | POST /api/v1/memories/search | 在指定用户的 schema 中搜索 |
| 自然语言召回 | POST /api/v1/memories/recall | 从指定用户的 schema 中召回 |

## 用户管理 API

### 列出所有用户

**API 端点**: `GET /api/v1/users`

**请求示例**:
```bash
curl -X GET "http://localhost:8000/api/v1/users"
```

### 获取用户信息

**API 端点**: `GET /api/v1/users/{user_id}`

**请求示例**:
```bash
curl -X GET "http://localhost:8000/api/v1/users/develop"
```

### 删除用户

**API 端点**: `DELETE /api/v1/users/{user_id}`

**请求示例**:
```bash
curl -X DELETE "http://localhost:8000/api/v1/users/test_user"
```

**注意**: 删除用户会删除该用户的所有数据，此操作不可恢复！

## 测试验证

### 运行测试脚本

```bash
cd projects/memory_recall
python test_multi_user.py
```

### 测试步骤

1. 验证迁移脚本执行
2. 验证 schema 创建
3. 测试 develop 用户
4. 测试 test 用户
5. 验证用户数据隔离性
6. 测试 schema 切换函数
7. 测试新用户初始化
8. 清理测试数据

## 数据库迁移

### 执行迁移

```bash
cd projects/memory_recall/apps/api/migrations
python run_migrations.py
```

迁移脚本会自动：
1. 创建 `users` 表
2. 创建 schema 管理函数
3. 初始化默认用户（develop、test）

### 回滚迁移

如果需要回滚，手动执行以下 SQL：

```sql
-- 删除 schema
DROP SCHEMA IF EXISTS user_develop CASCADE;
DROP SCHEMA IF EXISTS user_test CASCADE;

-- 删除用户表
DROP TABLE IF EXISTS public.users;

-- 删除函数
DROP FUNCTION IF EXISTS create_user_schema(VARCHAR);
DROP FUNCTION IF EXISTS set_user_schema(VARCHAR);
DROP FUNCTION IF EXISTS delete_user_schema(VARCHAR);
DROP FUNCTION IF EXISTS get_or_create_user_schema(VARCHAR);
```

## 开发者指南

### 在代码中使用

```python
from src.database import db

# 方法 1：直接切换 schema
await db.set_user_schema("develop")
# 然后执行数据库操作
await db.execute("INSERT INTO memories ...")

# 方法 2：使用上下文管理器
async with db.user_context("test"):
    # 在这个上下文中，所有数据库操作都在 test 用户的 schema 下
    await db.execute("INSERT INTO memories ...")
    await db.fetch("SELECT * FROM memories")
```

### 创建新用户

```python
# 初始化用户
result = await db.init_user("new_user")

print(f"用户 ID: {result['user_id']}")
print(f"Schema: {result['schema_name']}")
print(f"是否已存在: {result['already_exists']}")
```

## 最佳实践

1. **用户 ID 命名规范**
   - 使用有意义的名称（如用户名、邮箱前缀）
   - 只使用小写字母、数字和下划线
   - 避免使用特殊字符和空格

2. **数据隔离验证**
   - 定期检查用户数据隔离性
   - 使用测试脚本验证 schema 隔离

3. **性能优化**
   - 为每个 schema 创建必要的索引
   - 监控 schema 数量，避免过多 schema 影响性能

4. **安全性**
   - 验证 user_id 格式
   - 防止 SQL 注入（使用参数化查询）
   - 定期审计用户访问权限

## 故障排查

### 问题 1：用户已存在

**错误信息**: `User already exists: develop`

**解决方案**: 检查用户是否已创建，或使用不同的 user_id

### 问题 2：Schema 不存在

**错误信息**: `User not found: test_user`

**解决方案**: 先调用用户初始化 API 创建用户

### 问题 3：数据库连接失败

**错误信息**: `数据库连接失败`

**解决方案**: 检查数据库配置和连接参数

## 相关文档

- [API 文档](http://localhost:8000/docs)
- [数据库 Schema](../scripts/schema.sql)
- [迁移脚本](../apps/api/migrations/007_multi_user_schema.sql)
