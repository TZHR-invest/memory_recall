# Memory Recall - 通用记忆召回系统

**版本**：v0.3.1  
**状态**：生产可用  
**最后更新**：2026-03-26

---

## 项目定位

**核心目标**：
1. **首先解决人类记忆痛点**（时间追溯、事件召回、位置记忆、灵感捕捉）
2. **其次服务 AI Agent**（解决上下文窗口有限、模型注意力分散问题）

**核心特性**：
- ✅ Function Calling 方式提取记忆（稳定、高效）
- ✅ 智能实体提取（分级策略，过滤低价值实体）
- ✅ 自动构建知识图谱（实体+关系）
- ✅ 多用户 Schema 隔离（数据安全）
- ✅ 长文本自动分段（突破 LLM 上下文限制）
- ✅ 文件上传支持（txt、md、log）
- ✅ Web 前端界面
- ✅ 低温度提取（temperature=0.1，提高稳定性）

---

## 技术栈

| 组件 | 技术选择 | 说明 |
|------|---------|------|
| 数据库 | PostgreSQL 14+ | 关系型数据库 |
| 向量扩展 | pgvector | 向量相似度搜索 |
| LLM | 火山引擎 doubao-seed-2-0-mini | Function Calling |
| Embedding | doubao-embedding-vision | 文本向量化 |
| 后端框架 | FastAPI | 异步 API 框架 |
| 部署方式 | Docker / 本地 | 灵活部署 |

---

## 核心设计

### Function Calling 方式

使用 LLM Function Calling 一次性提取：
- **记忆内容**（可多条独立记忆，自动精炼）
- **时间信息**（标准化为 ISO 8601 格式）
- **实体**（分级提取，只保留高召回价值实体）
- **关系**（实体之间的语义关系）

### 实体提取分级策略

| 类型 | 提取策略 | 示例 |
|------|---------|------|
| person | ✅ 必须提取 | 张三、爸爸、妈妈 |
| location | ✅ 必须提取 | 星巴克、公司、家 |
| event | ✅ 只提取重要事件 | 面试、数学课、生日会 |
| topic | ⚠️ 有条件提取 | 新项目、旅行计划 |
| object | ⚠️ 只提取重要物品 | 钱包、钥匙、合同 |
| 日常行为 | ❌ 不提取 | 吃饭、睡觉、看书、散步 |

### 关键设计决策

| 设计项 | 决策 | 说明 |
|--------|------|------|
| "我"实体 | ❌ 不存储 | entities 表不存储"我"，避免冗余 |
| "我"关系 | ✅ 用 NULL 表示 | relations 表中"我"用 NULL 表示 |
| 时间标准化 | 只精确到日期 | 避免 LLM 推断具体时间 |
| 长文本处理 | 自动分段 | 超过 5000 字符自动分段 |
| temperature | 0.1 | 低温度提高提取稳定性 |
| 日常行为 | ❌ 不提取 | 吃饭、睡觉等无召回价值 |

---

## 项目结构

```
memory_recall/
├── apps/api/
│   ├── main.py              # API 主入口
│   ├── requirements.txt     # Python 依赖
│   ├── migrations/          # 数据库迁移
│   ├── scripts/             # 实用脚本
│   ├── src/
│   │   ├── routes/          # API 路由
│   │   │   ├── files.py     # 文件上传
│   │   │   ├── graph.py     # 图谱查询
│   │   │   ├── memories.py  # 记忆 CRUD
│   │   │   └── upload.py    # 上传接口
│   │   ├── services/        # 核心服务
│   │   │   ├── memory_service.py           # 记忆服务
│   │   │   ├── memory_extraction_service.py # 记忆提取
│   │   │   ├── graph_builder_service.py    # 图谱构建
│   │   │   ├── graph_recall_service.py     # 图谱召回
│   │   │   └── llm_recall_service.py       # LLM 召回
│   │   ├── tools/           # Function Calling 工具
│   │   │   └── extract_memories_tool.py    # 记忆提取工具
│   │   ├── models/          # 数据模型
│   │   ├── llm/             # LLM 客户端
│   │   ├── embedding/       # 向量编码
│   │   └── cache/           # 缓存
│   └── tests/               # 单元测试
├── web/
│   └── index.html           # Web 前端
├── docs/                    # 设计文档
├── README.md
└── DESIGN.md
```

---

## 快速开始

### 环境要求

- Python 3.10+
- PostgreSQL 14+ (with pgvector)
- Docker (可选)

### 安装依赖

```bash
cd apps/api
python -m venv venv
source venv/bin/activate  # Linux/macOS
# 或 venv\Scripts\activate  # Windows

pip install -r requirements.txt
```

### 配置环境变量

创建 `apps/api/.env` 文件：

```env
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/memory_recall
VOLC_API_KEY=your_api_key
VOLC_API_BASE=https://ark.cn-beijing.volces.com/api/v3
VOLC_LLM_MODEL=doubao-seed-2-0-mini-260215
VOLC_EMBEDDING_MODEL=doubao-embedding-vision-251215
```

### 运行数据库迁移

```bash
cd apps/api
python migrations/run_migrations.py
```

### 启动 API 服务

```bash
cd apps/api
source venv/bin/activate
uvicorn main:app --host 0.0.0.0 --port 8000
```

### 启动 Web 前端

```bash
cd web
./start.sh
# 或直接用浏览器打开 index.html
```

---

## API 接口

### 创建记忆

```bash
POST /api/v1/memories/with-graph
Content-Type: application/json

{
  "content": "今天下午在星巴克见了张三，聊了新项目。",
  "user_id": "test",
  "enable_graph": true
}
```

**返回**：
```json
{
  "success": true,
  "memory_id": "xxx-xxx-xxx",
  "graph": {
    "entities": [
      {"name": "张三", "type": "person"},
      {"name": "星巴克", "type": "location"},
      {"name": "新项目", "type": "topic"}
    ],
    "relations": [
      {"source": "我", "target": "星巴克", "relation_type": "at"},
      {"source": "我", "target": "张三", "relation_type": "met"},
      {"source": "我", "target": "新项目", "relation_type": "discussed"}
    ]
  }
}
```

### 上传文件

```bash
POST /api/v1/files/upload
Content-Type: multipart/form-data

file: your_file.txt
user_id: test
```

**支持格式**：txt、md、log（最大 10MB）

### 召回记忆（智能召回）

```bash
POST /api/v1/memories/recall
Content-Type: application/json

{
  "query": "张三的朋友",
  "user_id": "test",
  "limit": 10
}
```

**默认使用智能召回**：
- ✅ LLM 自动选择最佳召回策略（向量/关键词/图谱/时间/混合）
- ✅ 透明决策过程（返回策略选择原因）
- ✅ 图谱召回失败自动降级

**响应**：
```json
{
  "code": 200,
  "data": {
    "answer": "张三的朋友包括李四和王五...",
    "used_memories": [...],
    "memory_count": 2,
    "route_decision": {
      "strategy": "graph_recall",
      "reason": "查询涉及人物关系，适合图谱召回",
      "params": {"entity_name": "张三"}
    },
    "recall_mode": "smart_recall"
  }
}
```

**禁用智能召回**（使用混合召回）：
```json
{
  "query": "张三的朋友",
  "user_id": "test",
  "limit": 10,
  "use_smart_recall": false
}
```

### 智能召回（专用端点）

```bash
POST /api/v1/memories/smart-recall
Content-Type: application/json

{
  "query": "张三的朋友",
  "user_id": "test",
  "limit": 10
}
```

**与 `/recall` 的区别**：
- `/recall`: 通用端点，默认智能召回，可禁用
- `/smart-recall`: 专用端点，强制智能召回

### 查询图谱

```bash
GET /api/v1/graph/entities?user_id=test&limit=100
```

---

## 核心功能

### 1. 文本输入

- ✅ 自动提取记忆内容（精炼到 30-60 字）
- ✅ 自动提取实体（分级策略）
- ✅ 自动提取关系
- ✅ 时间标准化（只精确到日期）

### 2. 文件上传

- ✅ 支持 txt、md、log 格式
- ✅ 最大 10MB
- ✅ 自动分段处理（>5000 字符）
- ✅ 支持连续上传

### 3. 长文本处理

- ✅ 自动检测文本长度
- ✅ 超过 5000 字符自动分段
- ✅ 每段独立调用 LLM
- ✅ 去重后存储

### 4. 多用户支持

- ✅ 每个用户独立 Schema
- ✅ 数据完全隔离
- ✅ 自动创建用户 Schema

### 5. 智能召回（新功能）

- ✅ LLM 自动选择召回策略（Function Calling）
- ✅ 5 种召回方式：向量、关键词、图谱、时间、混合
- ✅ 透明决策过程
- ✅ 自动降级机制

---

## 数据模型

### 记忆表（memories）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID | 主键 |
| content | TEXT | 记忆内容（精炼后） |
| input_type | VARCHAR | 输入类型（text/file） |
| time_value | TIMESTAMP | 时间值 |
| location_name | TEXT | 地点名称 |
| people | JSONB | 人物列表 |
| file_name | TEXT | 文件名（文件上传时） |

### 实体表（entities）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID | 主键 |
| name | TEXT | 实体名称 |
| type | VARCHAR | 实体类型（person/location/event 等） |
| user_id | VARCHAR | 用户 ID |

### 关系表（relations）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID | 主键 |
| from_entity_id | UUID | 源实体（NULL 表示"我"） |
| to_entity_id | UUID | 目标实体 |
| relation_type | VARCHAR | 关系类型（at/met/discussed 等） |

---

## 测试

```bash
cd apps/api
pytest tests/
```

---

## 文档

- [设计文档](DESIGN.md)
- [API 文档](docs/API_DOCUMENTATION.md)
- [用户指南](docs/USER_GUIDE.md)
- [多用户指南](docs/MULTI_USER_GUIDE.md)
- [部署指南](docs/DEPLOYMENT.md)

---

## 更新日志

### v0.3.1 (2026-03-26)

**核心变更**：
- 添加 `classmate` 关系类型（正确识别同学关系）
- 修复关系提取问题（使用正确的 Function Calling 工具）
- 删除未使用的代码，精简项目结构

**修复**：
- 修复 `classmate` 关系提取问题（之前被错误识别为 `friend`）
- 更新 `EXTRACT_MEMORIES_TOOL` 添加 `classmate` 关系类型
- 添加同学关系提取示例

**清理**：
- 删除 `graph_builder_service.py` 中未使用的方法：
  - `build_graph`、`extract_entities`、`infer_relations`
  - `_extract_entities`、`_extract_relations`、`_find_similar_entities`
  - `_create_memory_entity_link`、`_parse_entities_from_json`、`_parse_relations_from_json`
  - `_get_existing_entities`、`_get_existing_relations`
- 删除 `memory_service.py` 中未使用的 `batch_create_memories` 方法
- 删除 `prompts.py` 中未使用的 `RELATION_EXTRACTION_PROMPT`
- 删除 `graph_tools.py` 中未使用的 `ESTABLISH_RELATIONS_TOOL`

### v0.3.0 (2026-03-24)

**核心变更**：
- 实现实体提取分级策略（过滤低价值实体）
- 降低 temperature 到 0.1（提高提取稳定性）
- 优化记忆内容精炼规则（30-60 字）
- 添加更多关系类型（used, experienced）
- 修复关系查询的 JOIN 问题

**改进**：
- 只提取有召回价值的实体（过滤日常行为）
- 过滤日常物品和泛化概念
- 记忆内容自动精炼
- 优化 prompt 结构（添加示例）

**清理**：
- 删除调试脚本和临时测试文件
- 删除过时设计文档
- 删除测试报告和缓存文件

### v0.2.0 (2026-03-22)

**核心变更**：
- 重构为 Function Calling 方式
- 删除旧的 Prompt+JSON 处理方式
- 添加时间标准化（带 UTC 时区）
- 支持长文本自动分段
- 支持文件上传
- 修复 memory_entities 外键约束
- 清理项目结构

**改进**：
- entities 表不存储"我"
- relations 表中"我"用 NULL 表示
- 所有输入统一使用 Function Calling
- Web 前端优化（支持连续上传）

### v0.1.0 (2026-03-19)

- 初始版本
- 基础记忆存储和召回
- 文本输入处理
- Web 前端

---

## 许可证

MIT License

---

*创建者：颓弟*  
*创建时间：2026-03-19*  
*最后更新：2026-03-26*
