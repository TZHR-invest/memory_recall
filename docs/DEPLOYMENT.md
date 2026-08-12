# Memory Recall 部署文档

> 状态: ACTIVE · 版本: v1.0 · 最后更新: 2026-08-12

## 部署方式概览

| 方式 | 适用场景 | 说明 |
|------|---------|------|
| Docker Compose（推荐） | 本地试用/快速部署 | API + PostgreSQL(pgvector) + Adminer + Web 静态页 |
| 手动 venv | 开发/调试 | macOS/Ubuntu 本地直跑，schema 手动初始化 |

## 方式一：Docker Compose

```bash
cd apps/api
cp .env.example .env
# 编辑 .env：至少填 VOLC_API_KEY（LLM + embedding 必需）
docker compose up -d
```

启动内容：

- API：http://localhost:8000（Swagger: /docs）
- PostgreSQL：localhost:5432（pgvector/pgvector:pg16）
- Adminer：http://localhost:8888
- Web 仪表盘：http://localhost:3000

首次启动时 `docker-entrypoint-initdb.d/` 自动建库建表；已有卷时不会重复执行。
改 schema 后需要重建卷或手动执行迁移（见"数据库初始化"）。

## 方式二：手动部署（venv）

### 1. 环境要求

- Python 3.10+（macOS 系统自带 3.9 过旧，无法安装 fastapi==0.135.1 等依赖，必须建 venv）；
- PostgreSQL 14+ 且启用 pgvector 扩展；
- 火山引擎 API Key（`VOLC_API_KEY`，LLM 与 embedding 共用）。

### 2. 安装依赖

```bash
cd apps/api
python3 -m venv venv
venv/bin/pip install -r requirements.txt
```

### 3. 配置环境变量

```bash
cp .env.example .env
```

实际生效的数据库变量是 **五件套**：

```bash
DATABASE_HOST=localhost
DATABASE_PORT=5432
DATABASE_NAME=memory_recall
DATABASE_USER=postgres
DATABASE_PASSWORD=your_password
```

> 注意：`.env.example` 中的 `DATABASE_URL` 不会被解析（`src/database.py` 只读五件套），
> 填了也不生效，见 [ISSUES.md](ISSUES.md)。

必须配置：`VOLC_API_KEY`；无 Key 时记忆创建（embedding）、实体提取、关系检测全部失败。
可选：`LLM_PROVIDER=volcengine|deepseek`，embedding 始终走火山。

### 4. 初始化数据库

```bash
# 完整初始化：建库 + pgvector 扩展 + schema.sql 全部表
venv/bin/python setup_database.py

# 或仅建表（数据库已存在时）
venv/bin/python init_db.py
```

> 无迁移框架：schema.sql 是唯一事实源，改 schema 后需重跑上述脚本或手工 DDL。

### 5. 启动服务

```bash
cd apps/api
venv/bin/python -m uvicorn main:app --reload --port 8000
```

**必须从 `apps/api/` 目录启动**（代码使用绝对 `src.*` 导入）。

## 验证

```bash
curl http://localhost:8000/health
# {"status":"healthy",...}
curl http://localhost:8000/docs   # Swagger UI
```

创建 API Key（admin key）：

```bash
curl -X POST http://localhost:8000/auth/api-keys \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <admin-key>" \
  -d '{"user_name":"dev"}'
```

> 所有端点要求 `X-API-Key`（`rk_live_...` / `rk_test_...`），
> 容器隔离规则见 AGENTS.md 的 `verify_container_ownership`。

## 故障排查

| 症状 | 原因 | 处理 |
|------|------|------|
| 启动报 pgvector 未启用 | 扩展未安装/未创建 | `CREATE EXTENSION IF NOT EXISTS vector;` 或重跑 setup_database.py |
| 依赖安装失败（macOS） | 系统 Python 3.9 过旧 | 用 `python3.11+ -m venv venv` 创建 |
| 记忆创建/召回空结果 | VOLC_API_KEY 缺失或失效 | 检查 .env 与日志；`/debug/embedding-logs` 查看调用失败 |
| 连接失败 | 五件套配置错误 | 确认 DATABASE_HOST/PORT/NAME/USER/PASSWORD（不是 DATABASE_URL） |

## 备份与恢复

```bash
# 备份
pg_dump -U postgres -h localhost memory_recall > backup_$(date +%Y%m%d).sql

# 恢复
psql -U postgres -h localhost -d memory_recall < backup_YYYYMMDD.sql
```

## 生产建议

1. 关闭 `APP_DEBUG`，避免 500 错误泄露内部信息；
2. 反代启用 HTTPS，限制 Adminer/仪表盘访问；
3. 定期备份（记忆数据不可重建）；
4. 按需调整 `TRACE_ENABLED`/`TRACE_SAMPLE_RATE`（生产可降采样）。

*状态: ACTIVE · 版本: v1.0 · 最后更新: 2026-08-12*
