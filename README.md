# Memory Recall - 统一记忆系统

**版本**：v5.2.1  
**状态**：生产就绪  
**最后更新**：2026-04-07

---

## 项目定位

**核心目标**：
1. 简化架构，提升性能（召回延迟从 1.5-4 秒降到 ~50ms）
2. 统一 API 入口（合并 v1/v2 为单一版本）
3. 完整认证支持（API Key + 权限控制 + 速率限制）
4. 用户画像分离（static/dynamic 区分，精准上下文注入）

**核心特性**：
- ✅ 统一 API（单一入口，无版本前缀）
- ✅ 完整认证系统（API Key + 容器所有权验证）
- ✅ 简化数据模型（3 核心表：memories, relations, profiles）
- ✅ 时间语义关系（updates/extends/derives）
- ✅ 用户画像分离（static/dynamic）
- ✅ 知识图谱 API（可视化支持）
- ✅ 中文实体提取（ASMR 6维度）

---

## 项目结构

```
memory_recall/
├── apps/api/                    # 核心后端服务
│   ├── src/
│   │   ├── api/                 # API 端点（memories, auth, graph）
│   │   ├── services/
│   │   │   ├── core/            # 核心服务
│   │   │   │   ├── memory_store.py      # 记忆存储
│   │   │   │   ├── relation_service.py  # 关系管理
│   │   │   │   ├── profile_service.py   # 用户画像
│   │   │   │   ├── entity_extraction.py # 实体提取
│   │   │   │   ├── document_processor.py # 文档处理
│   │   │   │   └── chunking/            # AST-aware 文档分块
│   │   │   └── ...
│   │   ├── plugins/             # OpenClaw/OpenCode 插件
│   │   ├── llm/                 # LLM 客户端
│   │   └── embedding/           # 向量嵌入
│   ├── schema.sql              # 数据库结构（新环境初始化）
│   ├── init_db.py              # 数据库初始化脚本
│   └── tests/                   # 测试用例
├── docs/                        # 设计文档
└── web/                         # 前端界面
```

---

## 技术栈

| 组件 | 技术选择 | 说明 |
|------|---------|------|
| 数据库 | PostgreSQL 14+ | 关系型数据库 |
| 向量扩展 | pgvector | 向量相似度搜索 |
| LLM | 火山引擎 doubao-seed-2-0-mini | 文本处理 |
| Embedding | doubao-embedding-vision | 文本向量化 |
| 后端框架 | FastAPI | 异步 API 框架 |

---

## 核心架构

### 简化记忆架构（v5.0）

```
┌─────────────────────────────────────────────────────────────┐
│                    简化记忆架构                              │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  memories (核心表)                                          │
│  ├─ is_static: TRUE  → 永久特征（姓名、职业、偏好）         │
│  └─ is_static: FALSE → 最近活动（项目、兴趣）               │
│           │                                                 │
│           ↓ 三种关系                                        │
│           │                                                 │
│  memory_relations                                           │
│  ├─ updates: 信息更新（"我在 Google" → "我在 Supermemory"）  │
│  ├─ extends: 信息丰富（添加更多上下文）                      │
│  └─ derives: 信息推断（从模式推断新知识）                    │
│           │                                                 │
│           ↓ 缓存                                            │
│           │                                                 │
│  memory_profiles                                            │
│  └─ static + dynamic 缓存（~50ms 获取）                     │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Entity Graph 架构（v5.1）

```
┌─────────────────────────────────────────────────────────────┐
│                    Entity Graph 架构                         │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  entities (实体表)                                          │
│  ├─ name: 实体名称（"张三"、"字节跳动"、"北京"）            │
│  ├─ type: 实体类型（person/location/organization/event）    │
│  └─ mention_count: 提及次数                                 │
│           │                                                 │
│           ↓ 实体关系                                        │
│           │                                                 │
│  entity_relations                                           │
│  ├─ friend: 朋友关系                                        │
│  ├─ colleague: 同事关系                                     │
│  ├─ works_at: 工作关系                                      │
│  ├─ lives_at: 居住关系                                      │
│  └─ ... 更多关系类型                                        │
│           │                                                 │
│           ↓ 记忆关联                                        │
│           │                                                 │
│  memory_entities                                            │
│  └─ 记忆 ↔ 实体 多对多关联                                  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 双图谱召回系统

```
┌─────────────────────────────────────────────────────────────┐
│                    双图谱召回流程                            │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  用户查询 "张三在哪里工作？"                                 │
│           │                                                 │
│           ↓                                                 │
│  ┌─────────────────┐                                        │
│  │  1. Vector Search │ 语义相似度匹配                       │
│  └────────┬────────┘                                        │
│           │                                                 │
│           ↓                                                 │
│  ┌─────────────────┐                                        │
│  │ 2. Memory Graph │ 遍历记忆演进关系（updates/extends）    │
│  └────────┬────────┘                                        │
│           │                                                 │
│           ↓                                                 │
│  ┌─────────────────┐                                        │
│  │ 3. Entity Graph │ 遍历实体关系网络（张三--works_at-->?） │
│  └────────┬────────┘                                        │
│           │                                                 │
│           ↓                                                 │
│  ┌─────────────────┐                                        │
│  │ 4. Merge & Dedup │ 合并去重后返回                        │
│  └─────────────────┘                                        │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Profile API (~50ms)

```python
profile = await client.get_profile(container_tag="user_123")

# 返回：
{
    "profile": {
        "static": ["John Doe", "高级工程师", "喜欢暗黑模式"],
        "dynamic": ["正在做认证迁移", "调试速率限制"]
    },
    "searchResults": [...]  # 可选
}
```

---

## 快速开始

### 环境要求

- Python 3.10+
- PostgreSQL 14+ (with pgvector)

### 安装依赖

```bash
cd apps/api
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 配置环境变量

创建 `apps/api/.env` 文件：

```env
DATABASE_HOST=localhost
DATABASE_PORT=5432
DATABASE_NAME=memory_recall
DATABASE_USER=postgres
DATABASE_PASSWORD=postgres
VOLC_API_KEY=your_api_key
VOLC_API_BASE=https://ark.cn-beijing.volces.com/api/v3
VOLC_LLM_MODEL=doubao-seed-2-0-mini-260215
VOLC_EMBEDDING_MODEL=doubao-embedding-vision-251215
```

### 初始化数据库

**方式一：完整初始化（推荐新环境）**

使用 `setup_database.py` 自动创建数据库和表：

```bash
cd apps/api
python setup_database.py
```

此脚本会：
1. 连接到 PostgreSQL 服务器
2. 创建数据库（如果不存在）
3. 安装 pgvector 扩展
4. 创建所有表和索引

**方式二：仅创建表（数据库已存在时）**

如果数据库已存在，使用 `init_db.py`：

```bash
cd apps/api
python init_db.py
```

**注意**：不再需要运行迁移脚本，schema.sql 包含完整的数据库结构。

### 启动 API 服务

```bash
cd apps/api
source venv/bin/activate
uvicorn main:app --host 0.0.0.0 --port 8000
```

---

## Docker 部署

### 使用 Docker Compose（推荐）

```bash
cd apps/api

# 启动所有服务（首次启动会自动创建数据库和表）
docker-compose up -d

# 查看服务状态
docker-compose ps

# 查看日志
docker-compose logs -f postgres  # 查看数据库初始化日志
docker-compose logs -f api       # 查看 API 日志
```

**首次启动自动完成**：
1. 创建 `memory_recall` 数据库
2. 安装 pgvector 扩展
3. 创建所有表和索引

**重置数据库**（删除所有数据重新初始化）：
```bash
docker-compose down -v  # 删除数据卷
docker-compose up -d    # 重新启动
```

### 服务地址

| 服务 | 地址 | 说明 |
|------|------|------|
| API | http://localhost:8000 | FastAPI 服务 |
| API 文档 | http://localhost:8000/docs | Swagger UI |
| pgAdmin | http://localhost:5050 | 数据库管理界面 |
| PostgreSQL | localhost:5432 | 数据库连接 |

### pgAdmin 登录

- **邮箱**: admin@local.com
- **密码**: admin123

### 停止服务

```bash
docker-compose down

# 删除数据卷（清空数据）
docker-compose down -v
```

---

## API 接口

**认证**: 所有端点需要 `X-API-Key` header。

### 创建 API Key

```bash
POST /auth/keys
X-API-Key: <admin_key>
Content-Type: application/json

{
    "name": "My API Key",
    "permissions": ["read", "write"],
    "is_test": false
}
```

### 创建记忆

```bash
POST /memories
X-API-Key: <your-api-key>
Content-Type: application/json

{
    "content": "我是素食主义者，不喜欢吃肉",
    "container_tag": "user_001",
    "is_static": true
}
```

### 获取用户画像

```bash
GET /profile?container_tag=user_001&query=饮食偏好
X-API-Key: <your-api-key>
```

### 搜索记忆

```bash
POST /search
X-API-Key: <your-api-key>
Content-Type: application/json

{
    "query": "饮食偏好",
    "container_tag": "user_001",
    "limit": 10,
    "threshold": 0.6
}
```

### 知识图谱

```bash
GET /graph?container_tag=user_001
X-API-Key: <your-api-key>
```

### 遗忘记忆

```bash
POST /memories/{memory_id}/forget
X-API-Key: <your-api-key>
```

### 恢复记忆

```bash
POST /memories/{memory_id}/restore
X-API-Key: <your-api-key>
```

### 更新记忆版本

```bash
POST /memories/{memory_id}/update
X-API-Key: <your-api-key>
Content-Type: application/json

{
    "content": "我现在在 Supermemory 工作"
}
```

---

## OpenClaw 插件

### 安装

```bash
openclaw plugins install memory-recall
```

### 配置

```json
{
    "apiKey": "your-api-key",
    "baseUrl": "http://localhost:8000",
    "containerTag": "openclaw_default",
    "autoRecall": true,
    "autoCapture": true,
    "maxRecallResults": 10
}
```

### 可用 Tools

| Tool | 说明 |
|------|------|
| `memory_store` | 存储记忆 |
| `memory_search` | 搜索记忆 |
| `memory_profile` | 获取用户画像 |
| `memory_forget` | 删除记忆 |

---

## OpenCode 插件

### 安装

```bash
bunx memory-recall-opencode install
```

### 配置

插件使用 `keyId` 自动生成项目隔离的 container_tag：

```json
{
    "apiKey": "your-api-key",
    "baseUrl": "http://localhost:8000",
    "userName": "YourName",
    "keyId": "b262d2f1-6232-49f4-820e-3f5e4cf6b956",
    "injectionStrategy": "smart",
    "initialInjection": {
        "profile": true,
        "projectMemories": true,
        "chunks": true,
        "maxChunks": 3
    },
    "smartRecall": {
        "enabled": true,
        "keywords": ["记得", "recall", "之前"],
        "maxAdditionalMemories": 3,
        "maxAdditionalChunks": 2
    },
    "enableGraphRecall": true,
    "enableEntityRecall": true,
    "graphMaxDepth": 2,
    "graphMaxNodes": 5
}
```

### 项目隔离（v5.1.6 新增）

插件自动为每个项目生成独立的 container_tag，实现数据隔离：

```
keyId: b262d2f1-6232-49f4-820e-3f5e4cf6b956

用户画像 container: b262d2f1-6232-49f4-820e-3f5e4cf6b956
项目 A container: b262d2f1-6232-49f4-820e-3f5e4cf6b956_project-memory_recall
项目 B container: b262d2f1-6232-49f4-820e-3f5e4cf6b956_project-shuihu_card_game
```

**隔离效果**：
- 用户画像：跨项目共享（偏好、习惯等）
- 项目记忆：按项目隔离（架构决策、Session Summary 等）
- 项目文档：按项目隔离（README、AGENTS.md 等）
```

### 智能注入策略

插件支持三种注入策略，优化 token 消耗和上下文相关性：

| 策略 | 说明 |
|------|------|
| `once` | 仅在 session 首条消息注入上下文 |
| `smart` | 首次注入 + 关键词触发召回（**默认**） |
| `always` | 每条消息都注入上下文（旧行为） |

**首次注入配置**：

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `initialInjection.profile` | `true` | 是否注入用户画像 |
| `initialInjection.projectMemories` | `true` | 是否注入项目记忆 |
| `initialInjection.chunks` | `true` | 是否注入文档 chunks |
| `initialInjection.maxChunks` | `3` | 首次注入的最大 chunks 数量 |

**智能召回配置**：

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `smartRecall.enabled` | `true` | 是否启用智能召回 |
| `smartRecall.keywords` | 内置关键词 | 触发召回的关键词列表 |
| `smartRecall.maxAdditionalMemories` | `3` | 每次召回的最大记忆数 |
| `smartRecall.maxAdditionalChunks` | `2` | 每次召回的最大 chunks 数 |

**默认召回关键词**：
```
中文：记得、之前、上次、以前、回忆、记忆
英文：recall、remember、previous、earlier
```

**迁移指南**：

旧配置（已废弃）：
```json
{
    "enableSmartRecall": true
}
```

新配置：
```json
{
    "injectionStrategy": "smart"
}
```

保持旧行为：
```json
{
    "injectionStrategy": "always"
}
```

### 三层召回机制

插件使用三层召回策略，提供更完整的上下文：

| 召回层 | 权重 | 说明 |
|--------|------|------|
| 向量搜索 | 50% | 语义相似度匹配 |
| 关系扩展 | 30% | 沿 `updates/extends/derives` 边遍历 |
| 实体关联 | 20% | 共享实体的记忆 |

**评分公式**：
```
final_score = vector_similarity × 0.5 + relation_score × 0.3 + entity_match_score × 0.2
```

### 关系类型优先级

| 关系 | 权重 | 说明 |
|------|------|------|
| `updates` | 1.0 | 信息演进链（最高优先级） |
| `extends` | 0.7 | 信息补充 |
| `derives` | 0.5 | 信息推断 |

### 实体类型权重

| 实体类型 | 权重 | 示例 |
|---------|------|------|
| `person` | 1.0 | 人名匹配 |
| `organization` | 0.9 | 公司/组织 |
| `location` | 0.8 | 地点 |
| `preference` | 0.7 | 偏好 |
| `time` | 0.5 | 时间 |

### 智能召回机制

插件支持每条消息智能召回，动态调整上下文注入：

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `enableSmartRecall` | `true` | 每条消息触发召回（关闭则仅首条消息注入） |
| `maxInjectedMemoryIds` | `100` | 跟踪的最大已注入记忆 ID（LRU 淘汰） |
| `recallThreshold` | `0.5` | 召回相似度阈值 |
| `dynamicRecallSize` | `true` | 根据对话长度动态调整召回数量 |

**动态召回公式**：
```
recall_count = max(2, maxMemories × (1 - min(0.5, conversationLength × 0.05)))
```

**去重机制**：
1. ID 去重：排除已注入的记忆 ID
2. 相似度过滤：只保留 `similarity >= threshold` 的结果
3. 对话历史过滤：排除已在对话中出现的内容

### 自动 Compaction

当上下文使用率达到阈值时，插件自动触发 compaction：

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `compactionThreshold` | `0.8` | 触发 compaction 的上下文使用率阈值 |
| `enableSummaryCapture` | `true` | 自动保存会话摘要为项目记忆 |
| `enableEventHandling` | `true` | 启用事件处理（compaction 触发） |

**Compaction 流程**：
1. 监听 `message.updated` 事件
2. 当上下文使用率 >= 阈值时触发 compaction
3. 生成会话摘要并注入项目知识
4. 摘要保存为项目记忆（带 `[会话摘要]` 前缀）

### 异步写入队列（v1.7.0+）

插件支持异步写入队列，将工具响应时间从 200-500ms 降至 < 10ms：

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `asyncQueue.enabled` | `true` | 是否启用异步队列 |
| `asyncQueue.maxConcurrency` | `3` | 最大并发任务数 |
| `asyncQueue.maxSize` | `100` | 队列最大容量 |
| `asyncQueue.taskTimeoutMs` | `120000` | 单任务超时（2分钟） |
| `asyncQueue.retryPolicy` | 内置策略 | 重试策略配置 |

**支持异步的操作**：
- `add` mode：添加记忆异步入队
- `import-docs` mode：每个文档独立任务入队
- FileWatcher：文件变化自动入队

**配置示例**：
```json
{
    "asyncQueue": {
        "enabled": true,
        "maxConcurrency": 3,
        "maxSize": 100,
        "taskTimeoutMs": 120000,
        "retryPolicy": {
            "maxRetries": 3,
            "baseDelayMs": 1000,
            "maxDelayMs": 30000
        }
    }
}
```

### 统一 Tool

```json
{
    "name": "memory-recall",
    "modes": ["add", "search", "profile", "list", "forget", "import-docs"],
    "scopes": ["user", "project"]
}
```

---

## 客户端使用

### 异步客户端

```python
from src.client import MemoryRecallClient

async with MemoryRecallClient(base_url="http://localhost:8000") as client:
    # 添加记忆
    result = await client.add_memory(
        content="用户喜欢暗黑模式",
        container_tag="user_123",
        is_static=True,
    )
    
    # 获取画像
    profile = await client.get_profile(container_tag="user_123")
    
    # 搜索
    results = await client.search(
        query="编程偏好",
        container_tag="user_123",
    )
```

### 同步客户端

```python
from src.client import SyncMemoryRecallClient

client = SyncMemoryRecallClient(base_url="http://localhost:8000")
result = client.add_memory(
    content="用户喜欢暗黑模式",
    container_tag="user_123",
    is_static=True,
)
client.close()
```

---

## 数据模型

### 记忆表（memories）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | VARCHAR(24) | 主键（mem_xxx） |
| container_tag | VARCHAR(100) | 隔离标识 |
| content | TEXT | 记忆内容 |
| embedding | VECTOR(1024) | 向量嵌入 |
| is_static | BOOLEAN | 是否永久特征 |
| is_latest | BOOLEAN | 是否最新版本 |
| valid_from | TIMESTAMP | 生效时间 |
| valid_until | TIMESTAMP | 失效时间 |
| metadata | JSONB | 元数据 |
| is_forgotten | BOOLEAN | 软删除标记 |

### 关系表（memory_relations）

| 字段 | 类型 | 说明 |
|------|------|------|
| from_memory_id | VARCHAR(24) | 源记忆 |
| to_memory_id | VARCHAR(24) | 目标记忆 |
| relation_type | VARCHAR(20) | updates/extends/derives |

### 画像表（memory_profiles）

| 字段 | 类型 | 说明 |
|------|------|------|
| container_tag | VARCHAR(100) | 主键 |
| static_memories | JSONB | 静态记忆列表 |
| dynamic_memories | JSONB | 动态记忆列表 |

### 实体表（entities）- v5.1 新增

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID | 主键 |
| name | VARCHAR(255) | 实体名称 |
| type | VARCHAR(50) | 实体类型（person/location/organization/event） |
| container_tag | VARCHAR(100) | 容器标识 |
| mention_count | INT | 提及次数 |
| confidence | FLOAT | 置信度 |

### 实体关系表（entity_relations）- v5.1 新增

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID | 主键 |
| from_entity_id | UUID | 源实体 |
| to_entity_id | UUID | 目标实体 |
| relation_type | VARCHAR(50) | 关系类型（friend/colleague/works_at/lives_at 等） |
| weight | FLOAT | 关系权重 |
| container_tag | VARCHAR(100) | 容器标识 |
| source_memory_id | VARCHAR(24) | 来源记忆 |

### 记忆-实体关联表（memory_entities）- v5.1 新增

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID | 主键 |
| memory_id | VARCHAR(24) | 记忆 ID |
| entity_id | UUID | 实体 ID |
| entity_type | VARCHAR(50) | 实体类型（冗余，便于查询） |

---

## 关键变更

### v5.2.0 (2026-04-07)

#### 新增功能

- **一次 API 调用完成所有召回**: 首次注入和智能召回都只需调用一次 `/context-inject` API
- **用户文档支持**: 新增用户级别文档存储和召回
- **文档来源信息**: chunks 召回时显示 title 和 source（文件路径）
- **统一注入 API**: 同时支持 `user_tag` + `project_tag` 参数

#### 架构改进

- **API 调用优化**: 从 2 次调用减少到 1 次（50% 减少）
- **延迟优化**: 从 ~150-250ms 减少到 ~100-200ms（~30% 减少）
- **向后兼容**: 旧的 `container_tag` 方式仍然支持

#### API 变更

- `POST /context-inject` 新增参数：
  - `user_tag`: 用户容器标识（用户画像、用户记忆、用户文档）
  - `project_tag`: 项目容器标识（项目记忆、项目文档）
  - 返回值新增：`user_memories`、`user_chunks`、`project_memories_count`、`user_memories_count`

#### 插件版本

- **OpenCode 插件**: 1.8.1 → 1.9.0
  - 修改 `client.ts` 的 `injectContext` 方法签名
  - 修改 `context.ts` 的 `injectContextFromBackend` 从调用两次改为一次

#### 性能对比

| 指标 | v5.1 | v5.2 | 提升 |
|------|------|------|------|
| API 调用次数 | 2 次 | 1 次 | 50% |
| 网络延迟 | ~150-250ms | ~100-200ms | ~30% |

### v5.1.10 (2026-04-06)

#### 新增功能

- **压缩时保留 AI 行为指导**: 压缩后 AI 仍然知道如何使用 Memory Recall 工具
- **修复三种注入策略**: `once`/`smart`/`always` 策略下压缩后都能保留行为指导

#### 插件版本

- **OpenCode 插件**: 1.8.0 → 1.8.1
  - 修改 `index.ts` 在 `experimental.session.compacting` hook 中注入 AI 行为指导

### v5.1.9 (2026-04-05)

#### 新增功能

- **Session Summary 提取优化**: 移除【偏好/约束】部分，仅保留【发现/决策】和【明确约束】
- **减少上下文存储冗余**: 避免保存用户偏好重复信息（用户偏好已存储在 Profile 中）

### v5.1.8 (2026-04-05)

#### 新增功能

- **实体过滤机制**: 多层过滤（黑名单 + 格式校验 + 长度校验）
- **扩展黑名单**: 80+ 词（泛指名词、语言名称、动词状态等）

#### 修复

- 修复无意义实体入库问题（"用户"、"代码"、"技术"等不再入库）

### v5.1.7 (2026-04-04)

#### 新增功能

- **Session Summary 提取优化**: 只保存重要内容（偏好/约束、发现/决策、明确约束）
- **自动去重**: 避免重复存储相似内容
- **存储格式优化**: 从几千字压缩到几百字

#### 插件版本

- **OpenCode 插件**: 1.7.9 → 1.8.0
  - 新增 `summary-extractor.ts` 提取重要内容
  - 修改 `compaction.ts` 使用新提取逻辑

### v5.1.6 (2026-04-04)

#### 新增功能

- **项目隔离**: 自动为每个项目生成独立的 container_tag，项目记忆和文档按项目隔离
- **keyId 配置**: 插件配置改用 `keyId`，自动生成 `userTag` 和 `projectTag`
- **后端验证增强**: `verify_container_ownership` 支持前缀匹配，允许 `{keyId}_*` 格式

#### 架构改进

- **Session Summary 过滤**: 后端 `context_inject_service.py` 自动过滤 Session Summary
- **向后兼容**: 支持旧的 `userContainerTag`/`projectContainerTag` 配置

#### 插件版本

- **OpenCode 插件**: 1.7.8 → 1.7.9
  - CLI 使用 `keyId` 配置
  - 自动生成项目隔离的 container_tag

### v5.1.5 (2026-04-03)

#### 新增功能

- **AI 行为指导**: 上下文注入时自动添加行为指导，让 AI 优先使用 memory recall 召回记忆
- **Search 工具增强**: 支持双图谱召回参数（enableMemoryGraph/enableEntityGraph）
- **智能召回优化**: Session 开始注入 vs 智能召回区分明确，节省 68.9% Token

#### 架构改进

- **废弃代码清理**: 删除 `lossless_recall_service.py` 和 `smart_recall_service.py`
- **召回统一**: 所有召回功能统一到 `context_inject_service.py`
- **测试清理**: 删除 24 个废弃的测试文件

#### 插件版本

- **OpenCode 插件**: 1.7.5 → 1.7.8
  - 1.7.6: AI 行为指导功能
  - 1.7.8: Search 工具双图谱召回支持

#### 性能对比

| 功能 | Session 开始注入 | 智能召回 |
|------|-----------------|---------|
| Token 消耗 | ~4293 Token | ~1336 Token |
| 条目数 | 25 条 | 6 条 |
| 节省比例 | - | 68.9% |

### v5.1.0 (2026-04-02)

#### 新增功能

- **Entity Graph 架构**: 实体表、实体关系表、记忆-实体关联表
- **双图谱召回系统**: Vector Search + Memory Graph + Entity Graph 三层召回
- **实体关系类型**: 13 种预定义关系（friend/colleague/works_at/lives_at 等）
- **实体类型**: 6 种核心类型（person/organization/location/event/preference/thing）
- **Context Injection 增强**: 支持双图谱召回配置参数

#### API 变更

- `POST /context-inject` 新增参数：
  - `enable_memory_graph`: 启用 Memory Graph 召回
  - `enable_entity_graph`: 启用 Entity Graph 召回
  - `memory_graph_depth/nodes`: Memory Graph 配置
  - `entity_graph_depth/nodes`: Entity Graph 配uration

#### 数据库变更

- 新增 `entities` 表（实体存储）
- 新增 `entity_relations` 表（实体关系）
- 新增 `memory_entities` 表（记忆-实体关联）
- 新增索引：实体名称、关系端点、记忆-实体关联

### v5.0.0 (2026-03-29)

#### 新增功能

- **统一 API**: 合并 v1/v2 为单一入口，无版本前缀
- **完整认证**: API Key + 容器所有权验证 + 速率限制
- **一键安装**: `python install.py` 自动初始化
- **知识图谱 API**: `GET /graph` 端点
- **中文实体提取**: LLM 增强 + 无意义实体过滤
- **关系检测**: 中文语义标记识别
- **智能文档分块**: AST-aware chunking + 上下文化嵌入
- **项目文档跟踪**: 自动导入 README/AGENTS.md 等项目文档

#### 架构改进

- **简化容器所有权**: 一个 API Key = 一个 Container
- **文档分离存储**: documents + chunks 表（与 memories 分离）
- **上下文化嵌入**: 分块自动添加文件/类型/摘要上下文
- **自动配置**: 插件首次运行自动初始化

#### Breaking Changes

- 所有端点需要 `X-API-Key` 认证
- API 路径变更：`/v1/*` → `/*`（根路径）
- `container_tag` 自动使用 API Key ID

#### 性能提升

- 召回延迟：1.5-4 秒 → ~50ms
- 数据模型：6+ 表 → 3 核心表
- API 端点：30+ → 17（精简）
- 实体提取超时：5s → 300s（支持长文本）
- 文档向量化：使用上下文化内容，搜索更准确

---

## 许可证

MIT License

---

*创建者：颓弟*
*创建时间：2026-03-19*
*最后更新：2026-04-04*
