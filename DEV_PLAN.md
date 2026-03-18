# Memory Recall - 详细开发计划

> **执行方式**：专门开发 session 持续运行
> **通知群**：oc_ba770d101e21e73ee7018daf31481805
> **开始时间**：2026-03-19

---

## 执行规则

1. **按顺序执行**：从 Step 1 开始，完成后再执行 Step 2
2. **遇到阻塞**：在飞书群通知用户协助
3. **完成每步后**：git commit 并 push
4. **完成每个阶段后**：在飞书群汇报进度
5. **全部完成后**：在飞书群通知项目完成

---

## Phase 1: 项目骨架搭建

### Step 1: 创建项目目录结构

**目标**：按照架构文档创建完整的目录结构

**目录结构**：
```
memory_recall/
├── apps/
│   └── api/
│       ├── src/
│       │   ├── routes/         # API 路由
│       │   ├── services/       # 业务逻辑
│       │   ├── models/         # 数据模型
│       │   ├── llm/            # LLM 调用
│       │   ├── embedding/      # 向量化
│       │   ├── face/           # 人脸识别
│       │   └── utils/          # 工具函数
│       ├── tests/
│       ├── main.py
│       └── requirements.txt
├── packages/
│   └── shared/                 # 共享类型
│       └── types.py
├── scripts/
│   ├── init_db.py             # 数据库初始化
│   └── test_connection.py     # 连接测试
├── docker-compose.yml
├── Dockerfile
└── .env.example
```

**验收标准**：
- [ ] 所有目录创建完成
- [ ] 所有 __init__.py 文件创建
- [ ] requirements.txt 包含所有依赖

---

### Step 2: 数据库初始化

**目标**：创建 PostgreSQL + pgvector 数据库 schema

**任务**：
1. 创建 docker-compose.yml（PostgreSQL + pgvector）
2. 创建数据库初始化脚本（schema.sql）
3. 创建连接测试脚本

**Schema 文件**：参考 docs/data-model.md

**验收标准**：
- [ ] docker-compose up -d 成功启动
- [ ] 数据库表创建成功
- [ ] pgvector 扩展安装成功
- [ ] 连接测试通过

---

### Step 3: 基础 API 框架

**目标**：创建 FastAPI 应用骨架

**任务**：
1. 创建 main.py（FastAPI 应用入口）
2. 创建配置管理（config.py）
3. 创建数据库连接（database.py）
4. 创建基础路由（health check）

**验收标准**：
- [ ] uvicorn main:app 启动成功
- [ ] /health 返回 200
- [ ] 数据库连接正常

---

### Step 4: LLM 服务模块

**目标**：实现火山引擎 LLM 调用

**任务**：
1. 创建 llm/client.py（火山引擎 API 客户端）
2. 创建 llm/prompts.py（Prompt 模板）
3. 创建 llm/extractor.py（结构化提取）
4. 测试 API 调用

**验收标准**：
- [ ] LLM API 调用成功
- [ ] 结构化提取测试通过

---

### Step 5: Embedding 服务模块

**目标**：实现火山引擎 Embedding 调用

**任务**：
1. 创建 embedding/client.py（火山引擎 Embedding 客户端）
2. 测试文本向量化
3. 测试向量存储和检索

**验收标准**：
- [ ] Embedding API 调用成功
- [ ] 向量存储到数据库成功
- [ ] 向量检索测试通过

---

### Step 6: 记忆管理服务

**目标**：实现记忆的 CRUD 操作

**任务**：
1. 创建 models/memory.py（记忆数据模型）
2. 创建 services/memory_service.py（记忆管理服务）
3. 创建 routes/memories.py（记忆 API 路由）
4. 实现创建记忆 API
5. 实现查询记忆 API

**验收标准**：
- [ ] POST /api/memories 创建记忆成功
- [ ] GET /api/memories/:id 查询记忆成功
- [ ] 数据库存储正确

---

### Step 7: 文本输入处理

**目标**：实现文本输入的结构化提取流程

**任务**：
1. 创建 services/input_processor.py（输入处理服务）
2. 实现短文本处理
3. 实现长文本分段
4. 实现结构化提取
5. 实现询问判断逻辑

**验收标准**：
- [ ] 文本输入处理测试通过
- [ ] 结构化提取结果正确
- [ ] 询问逻辑判断正确

---

### Step 8: 召回服务

**目标**：实现记忆召回功能

**任务**：
1. 创建 services/recall_service.py（召回服务）
2. 创建 services/query_parser.py（查询解析）
3. 创建 services/retriever.py（检索器）
4. 创建 services/ranker.py（排序器）
5. 实现 POST /api/recall/search API

**验收标准**：
- [ ] 查询解析测试通过
- [ ] 向量检索测试通过
- [ ] 排序结果正确
- [ ] 召回 API 测试通过

---

### Step 9: 人脸识别模块

**目标**：实现人脸检测和识别功能

**任务**：
1. 创建 face/detector.py（人脸检测）
2. 创建 face/recognizer.py（人脸识别）
3. 创建 models/face_encoding.py（人脸特征模型）
4. 创建 services/person_service.py（人物管理服务）
5. 测试人脸检测和识别

**验收标准**：
- [ ] 人脸检测测试通过
- [ ] 人脸特征提取测试通过
- [ ] 人脸匹配测试通过

---

### Step 10: 图片输入处理

**目标**：实现图片输入的处理流程

**任务**：
1. 创建 services/image_processor.py（图片处理服务）
2. 实现 EXIF 信息提取
3. 实现多模态理解（调用 doubao-seed-2-0-pro）
4. 实现人脸检测集成
5. 实现 POST /api/input/image API

**验收标准**：
- [ ] EXIF 提取测试通过
- [ ] 多模态理解测试通过
- [ ] 图片输入处理测试通过

---

### Step 11: 测试和文档

**目标**：完善测试和文档

**任务**：
1. 编写单元测试
2. 编写集成测试
3. 更新 README.md
4. 创建 API 使用文档
5. 创建部署文档

**验收标准**：
- [ ] 测试覆盖率 > 60%
- [ ] 文档完整清晰

---

### Step 12: 部署验证

**目标**：验证完整部署流程

**任务**：
1. 创建 Dockerfile
2. 更新 docker-compose.yml
3. 本地部署测试
4. 验证所有 API

**验收标准**：
- [ ] docker-compose up -d 成功
- [ ] 所有 API 正常工作
- [ ] 完整流程测试通过

---

## Phase 1 完成标准

- [ ] 所有 Step 完成
- [ ] 测试通过
- [ ] 文档完整
- [ ] 本地部署成功
- [ ] Git push 到远端

---

## 阻塞处理

**遇到以下情况需要在飞书群通知**：

1. **需要 API Key**：火山引擎 API Key
2. **需要配置信息**：数据库密码等
3. **技术决策**：需要用户确认方案
4. **依赖问题**：安装失败、版本冲突
5. **环境问题**：Docker 启动失败等

**通知格式**：
```
🚨 memory_recall 开发阻塞

Step X: [步骤名称]
问题：[问题描述]
需要：[需要的协助]
```

---

## 进度汇报格式

**每个阶段完成后**：
```
📊 memory_recall 开发进度

Phase X 完成 ✅
- Step 1: ✅
- Step 2: ✅
...

下一步：Phase X+1
```
