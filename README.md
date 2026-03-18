# memory_recall - 通用记忆召回系统

**版本**：v0.1.0  
**状态**：开发中  
**创建时间**：2026-03-19

---

## 项目定位

**核心目标**：
1. **首先解决人类记忆痛点**（时间追溯、事件召回、位置记忆、灵感捕捉）
2. **其次服务 AI Agent**（解决上下文窗口有限、模型注意力分散问题）

## 技术栈

| 组件 | 技术选择 | 说明 |
|------|---------|------|
| 数据库 | PostgreSQL + pgvector | 关系型 + 向量搜索 |
| 向量模型 | doubao-embedding-vision-251215 | 多模态嵌入 |
| 人脸识别 | face_recognition | 图片人物识别 |
| LLM + 多模态 | doubao-seed-2-0-pro-260215 | 结构化提取 |
| 后端框架 | FastAPI | API 服务 |
| 部署方式 | Docker Compose | 容器化部署 |

## 项目结构

```
memory_recall/
├── src/
│   ├── core/
│   │   ├── extractor.py      # 结构化提取
│   │   ├── indexer.py        # 索引管理
│   │   └── recall.py         # 召回机制
│   ├── storage/
│   │   ├── database.py       # 数据库连接
│   │   └── models.py         # 数据模型
│   ├── api/
│   │   ├── routes.py         # API 路由
│   │   └── schemas.py        # API 模式
│   └── utils/
│       ├── ocr.py            # OCR 工具
│       └── asr.py            # ASR 工具
├── tests/
│   ├── test_extractor.py
│   ├── test_indexer.py
│   └── test_recall.py
├── config/
│   ├── config.yaml           # 配置文件
│   └── prompts/              # LLM prompts
├── docs/
│   ├── DESIGN.md             # 设计文档
│   └── API.md                # API 文档
├── requirements.txt
├── docker-compose.yml
└── README.md
```

## 快速开始

### 环境要求

- Python 3.10+
- PostgreSQL 14+ (with pgvector)
- Docker & Docker Compose (可选)

### 安装依赖

```bash
pip install -r requirements.txt
```

### 配置数据库

```bash
# 启动 PostgreSQL
docker-compose up -d postgres

# 初始化数据库
python scripts/init_db.py
```

### 运行服务

```bash
# 启动 API 服务
uvicorn src.api.routes:app --reload
```

## API 接口

### 添加记忆

```bash
POST /api/memories
Content-Type: application/json

{
  "content": "今天在咖啡店遇到老同学，聊了很久",
  "type": "text"
}
```

### 召回记忆

```bash
GET /api/memories?query=咖啡店&limit=10
```

## 开发计划

### Phase 1: MVP（当前）
- [ ] 文本输入 → 结构化记忆
- [ ] 时间/关键词/标签索引
- [ ] 基础召回功能

### Phase 2: 多模态
- [ ] 图片 OCR 识别
- [ ] 图片场景识别
- [ ] 图片记忆存储

### Phase 3: 生产化
- [ ] Web 界面
- [ ] 用户认证
- [ ] 部署优化

## 设计文档

详细设计见 [DESIGN.md](docs/DESIGN.md)

## 贡献指南

暂无

## 许可证

MIT License

---

*创建者：颓弟*  
*创建时间：2026-03-19*
