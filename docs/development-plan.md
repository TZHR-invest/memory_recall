# Memory Recall - 开发计划

> **文档说明**：本文档规划 memory_recall 的开发里程碑、迭代目标、目录结构和部署方案。

---

## 开发里程碑

### Phase 1: MVP（1-2 周）

**目标**：验证核心流程，实现基础功能

**功能清单**：

| 功能 | 优先级 | 状态 |
|------|--------|------|
| 技术栈确认 | P0 | ✅ 已完成 |
| 文本输入处理 | P0 | ⏳ 待开发 |
| 结构化信息提取 | P0 | ⏳ 待开发 |
| 记忆存储（PostgreSQL） | P0 | ⏳ 待开发 |
| 时间索引 | P0 | ⏳ 待开发 |
| 关键词索引 | P0 | ⏳ 待开发 |
| 标签索引 | P0 | ⏳ 待开发 |
| 向量索引（pgvector） | P0 | ⏳ 待开发 |
| 基础召回功能 | P0 | ⏳ 待开发 |
| 自然语言查询 | P1 | ⏳ 待开发 |
| RESTful API | P1 | ⏳ 待开发 |
| 智能询问机制 | P1 | ⏳ 待开发 |
| 单元测试 | P1 | ⏳ 待开发 |

**技术栈**：

| 组件 | 技术 |
|------|------|
| 编程语言 | Python 3.10+ |
| Web 框架 | FastAPI |
| 数据库 | PostgreSQL 14+ + pgvector |
| LLM | doubao-seed-2-0-pro-260215（火山引擎） |
| Embedding | doubao-embedding-vision-251215（火山引擎） |
| 人脸识别 | face_recognition（本地） |

**详细技术选型**：参见 [tech-stack.md](./tech-stack.md)

**下一步**：项目骨架搭建

**产出物**：
- ✅ 核心代码库
- ✅ 测试用例
- ✅ API 文档
- ✅ 部署脚本

---

### Phase 2: 多模态（2-3 周）

**目标**：支持图片输入，增强用户体验

**功能清单**：

| 功能 | 优先级 | 状态 |
|------|--------|------|
| 图片上传 | P0 | ⏳ 待开发 |
| EXIF 信息提取 | P0 | ⏳ 待开发 |
| OCR 文字识别 | P0 | ⏳ 待开发 |
| 场景识别 | P1 | ⏳ 待开发 |
| 人脸检测 | P0 | ⏳ 待开发 |
| 人脸识别 | P1 | ⏳ 待开发 |
| 人物档案管理 | P0 | ⏳ 待开发 |
| 人脸特征存储 | P0 | ⏳ 待开发 |
| 图片多模态理解 | P1 | ⏳ 待开发 |
| 人物关联查询 | P1 | ⏳ 待开发 |
| 位置反向地理编码 | P2 | ⏳ 待开发 |

**技术栈**：

| 组件 | 技术 |
|------|------|
| OCR | PaddleOCR |
| 人脸识别 | insightface |
| 场景识别 | CLIP / 百度图像识别 API |
| 多模态理解 | GPT-4 Vision |

**产出物**：
- ✅ 多模态处理模块
- ✅ 人物档案系统
- ✅ 图片记忆测试

---

### Phase 3: 生产化（3-4 周）

**目标**：生产环境部署，支持多用户

**功能清单**：

| 功能 | 优先级 | 状态 |
|------|--------|------|
| 用户认证 | P0 | ⏳ 待开发 |
| 多用户支持 | P0 | ⏳ 待开发 |
| 权限管理 | P1 | ⏳ 待开发 |
| 异步任务处理 | P0 | ⏳ 待开发 |
| 批量导入 | P1 | ⏳ 待开发 |
| 数据导出 | P1 | ⏳ 待开发 |
| Web 界面 | P1 | ⏳ 待开发 |
| 移动端适配 | P2 | ⏳ 待开发 |
| 监控和日志 | P1 | ⏳ 待开发 |
| 备份和恢复 | P1 | ⏳ 待开发 |

**技术栈**：

| 组件 | 技术 |
|------|------|
| 任务队列 | Celery + Redis |
| 前端 | React / Vue |
| 监控 | Prometheus + Grafana |
| 日志 | ELK Stack |
| 容器化 | Docker + Kubernetes |

**产出物**：
- ✅ 生产环境部署
- ✅ Web 管理界面
- ✅ 用户文档
- ✅ 运维手册

---

### Phase 4: 增强（4-5 周）

**目标**：增强召回能力，优化用户体验

**功能清单**：

| 功能 | 优先级 | 状态 |
|------|--------|------|
| 语音输入 | P1 | ⏳ 待开发 |
| 主动召回 | P1 | ⏳ 待开发 |
| 定期回顾 | P1 | ⏳ 待开发 |
| 纪念日提醒 | P2 | ⏳ 待开发 |
| 记忆关联 | P2 | ⏳ 待开发 |
| 知识图谱 | P2 | ⏳ 待开发 |
| 智能摘要 | P1 | ⏳ 待开发 |
| 记忆重要性评分 | P2 | ⏳ 待开发 |
| 隐私保护 | P1 | ⏳ 待开发 |
| 端到端加密 | P2 | ⏳ 待开发 |

**产出物**：
- ✅ 增强功能模块
- ✅ 用户隐私保护方案
- ✅ 性能优化报告

---

## 目录结构

```
memory_recall/
├── README.md                     # 项目说明
├── DESIGN.md                     # 设计文档
├── docs/                         # 详细文档
│   ├── README.md                 # 项目概述
│   ├── architecture.md           # 架构设计
│   ├── data-model.md             # 数据模型
│   ├── processing-pipeline.md    # 处理流程
│   ├── recall-mechanism.md       # 召回机制
│   ├── api-design.md             # API 设计
│   └── development-plan.md       # 开发计划
├── src/                          # 源代码
│   ├── __init__.py
│   ├── main.py                   # 应用入口
│   ├── config.py                 # 配置管理
│   ├── api/                      # API 层
│   │   ├── __init__.py
│   │   ├── memories.py           # 记忆管理 API
│   │   ├── input.py              # 输入处理 API
│   │   ├── persons.py            # 人物管理 API
│   │   ├── recall.py             # 召回 API
│   │   └── stats.py              # 统计 API
│   ├── services/                 # 服务层
│   │   ├── __init__.py
│   │   ├── memory_service.py     # 记忆服务
│   │   ├── person_service.py     # 人物服务
│   │   ├── recall_service.py     # 召回服务
│   │   └── llm_service.py        # LLM 服务
│   ├── processors/               # 处理器
│   │   ├── __init__.py
│   │   ├── text_processor.py     # 文本处理器
│   │   ├── image_processor.py    # 图片处理器
│   │   └── audio_processor.py    # 语音处理器
│   ├── models/                   # 数据模型
│   │   ├── __init__.py
│   │   ├── memory.py             # 记忆模型
│   │   ├── person.py             # 人物模型
│   │   └── face_feature.py       # 人脸特征模型
│   ├── storage/                  # 存储层
│   │   ├── __init__.py
│   │   ├── database.py           # 数据库连接
│   │   ├── memory_store.py       # 记忆存储
│   │   ├── person_store.py       # 人物存储
│   │   └── index_manager.py      # 索引管理
│   ├── retrieval/                # 检索层
│   │   ├── __init__.py
│   │   ├── query_parser.py       # 查询解析
│   │   ├── exact_filter.py       # 精确过滤
│   │   ├── semantic_search.py    # 语义搜索
│   │   ├── hybrid_retrieval.py   # 混合检索
│   │   └── ranking.py            # 排序算法
│   ├── nlp/                      # NLP 模块
│   │   ├── __init__.py
│   │   ├── extractor.py          # 信息提取
│   │   ├── inquiry_judge.py      # 询问判断
│   │   └── prompts/              # Prompt 模板
│   │       ├── extract_memory.txt
│   │       ├── parse_query.txt
│   │       └── judge_inquiry.txt
│   ├── vision/                   # 视觉模块
│   │   ├── __init__.py
│   │   ├── ocr.py                # OCR 处理
│   │   ├── face_detection.py     # 人脸检测
│   │   ├── face_recognition.py   # 人脸识别
│   │   └── scene_recognition.py  # 场景识别
│   └── utils/                    # 工具模块
│       ├── __init__.py
│       ├── logger.py             # 日志工具
│       ├── cache.py              # 缓存工具
│       └── helpers.py            # 辅助函数
├── tests/                        # 测试
│   ├── __init__.py
│   ├── conftest.py               # 测试配置
│   ├── test_api/                 # API 测试
│   │   ├── test_memories.py
│   │   ├── test_input.py
│   │   ├── test_persons.py
│   │   └── test_recall.py
│   ├── test_services/            # 服务测试
│   │   ├── test_memory_service.py
│   │   ├── test_person_service.py
│   │   └── test_recall_service.py
│   ├── test_processors/          # 处理器测试
│   │   ├── test_text_processor.py
│   │   └── test_image_processor.py
│   └── test_retrieval/           # 检索测试
│       ├── test_query_parser.py
│       ├── test_exact_filter.py
│       ├── test_semantic_search.py
│       └── test_ranking.py
├── scripts/                      # 脚本
│   ├── init_db.py                # 初始化数据库
│   ├── migrate.py                # 数据迁移
│   └── backup.py                 # 备份脚本
├── migrations/                   # 数据库迁移
│   ├── versions/
│   └── env.py
├── docker/                       # Docker 配置
│   ├── Dockerfile
│   ├── docker-compose.yml
│   └── nginx.conf
├── k8s/                          # Kubernetes 配置
│   ├── deployment.yaml
│   ├── service.yaml
│   └── configmap.yaml
├── requirements.txt              # Python 依赖
├── setup.py                      # 安装配置
├── .env.example                  # 环境变量示例
├── .gitignore
└── Makefile                      # Make 命令
```

---

## 部署方案

### 1. 本地开发环境

**环境要求**：
- Python 3.10+
- PostgreSQL 14+
- Redis（可选，用于缓存）

**部署步骤**：

```bash
# 1. 克隆项目
git clone https://github.com/your-org/memory_recall.git
cd memory_recall

# 2. 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate  # Windows

# 3. 安装依赖
pip install -r requirements.txt

# 4. 配置环境变量
cp .env.example .env
# 编辑 .env 文件，填入配置

# 5. 初始化数据库
python scripts/init_db.py

# 6. 启动服务
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

**环境变量配置**（`.env`）：

```bash
# 数据库配置
DATABASE_URL=postgresql://user:password@localhost:5432/memory_recall

# Redis 配置（可选）
REDIS_URL=redis://localhost:6379/0

# OpenAI 配置
OPENAI_API_KEY=sk-xxx
OPENAI_MODEL=gpt-4
OPENAI_EMBEDDING_MODEL=text-embedding-3-small

# OCR 配置
PADDLEOCR_USE_GPU=false

# 人脸识别配置
INSIGHTFACE_MODEL=buffalo_l

# 其他配置
LOG_LEVEL=INFO
ENVIRONMENT=development
```

---

### 2. Docker 部署

**Dockerfile**：

```dockerfile
# Dockerfile
FROM python:3.10-slim

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    postgresql-client \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# 设置工作目录
WORKDIR /app

# 复制依赖文件
COPY requirements.txt .

# 安装 Python 依赖
RUN pip install --no-cache-dir -r requirements.txt

# 复制代码
COPY . .

# 暴露端口
EXPOSE 8000

# 启动命令
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**docker-compose.yml**：

```yaml
version: '3.8'

services:
  postgres:
    image: pgvector/pgvector:pg14
    environment:
      POSTGRES_USER: memory_recall
      POSTGRES_PASSWORD: password
      POSTGRES_DB: memory_recall
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"
  
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
  
  app:
    build: .
    environment:
      DATABASE_URL: postgresql://memory_recall:password@postgres:5432/memory_recall
      REDIS_URL: redis://redis:6379/0
      OPENAI_API_KEY: ${OPENAI_API_KEY}
    ports:
      - "8000:8000"
    depends_on:
      - postgres
      - redis
  
  worker:
    build: .
    command: celery -A src.celery_app worker --loglevel=info
    environment:
      DATABASE_URL: postgresql://memory_recall:password@postgres:5432/memory_recall
      REDIS_URL: redis://redis:6379/0
      OPENAI_API_KEY: ${OPENAI_API_KEY}
    depends_on:
      - postgres
      - redis

volumes:
  postgres_data:
```

**部署步骤**：

```bash
# 1. 构建镜像
docker-compose build

# 2. 启动服务
docker-compose up -d

# 3. 初始化数据库
docker-compose exec app python scripts/init_db.py

# 4. 查看日志
docker-compose logs -f app
```

---

### 3. Kubernetes 部署

**deployment.yaml**：

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: memory-recall
  labels:
    app: memory-recall
spec:
  replicas: 3
  selector:
    matchLabels:
      app: memory-recall
  template:
    metadata:
      labels:
        app: memory-recall
    spec:
      containers:
      - name: memory-recall
        image: your-registry/memory-recall:latest
        ports:
        - containerPort: 8000
        env:
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: memory-recall-secrets
              key: database-url
        - name: OPENAI_API_KEY
          valueFrom:
            secretKeyRef:
              name: memory-recall-secrets
              key: openai-api-key
        resources:
          requests:
            memory: "512Mi"
            cpu: "500m"
          limits:
            memory: "1Gi"
            cpu: "1000m"
        livenessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /ready
            port: 8000
          initialDelaySeconds: 5
          periodSeconds: 5
```

**service.yaml**：

```yaml
apiVersion: v1
kind: Service
metadata:
  name: memory-recall
spec:
  selector:
    app: memory-recall
  ports:
  - protocol: TCP
    port: 80
    targetPort: 8000
  type: LoadBalancer
```

**部署步骤**：

```bash
# 1. 创建命名空间
kubectl create namespace memory-recall

# 2. 创建 Secret
kubectl create secret generic memory-recall-secrets \
  --from-literal=database-url='postgresql://...' \
  --from-literal=openai-api-key='sk-...' \
  -n memory-recall

# 3. 部署应用
kubectl apply -f k8s/deployment.yaml -n memory-recall
kubectl apply -f k8s/service.yaml -n memory-recall

# 4. 检查状态
kubectl get pods -n memory-recall
kubectl get services -n memory-recall
```

---

### 4. 云服务部署

#### 4.1 AWS 部署

**架构**：
- **ECS**：运行容器化应用
- **RDS**：PostgreSQL 数据库（启用 pgvector）
- **ElastiCache**：Redis 缓存
- **S3**：存储图片和附件
- **CloudFront**：CDN 加速
- **ALB**：负载均衡

**部署步骤**：

```bash
# 1. 创建 ECR 仓库
aws ecr create-repository --repository-name memory-recall

# 2. 构建并推送镜像
docker build -t memory-recall .
docker tag memory-recall:latest <account-id>.dkr.ecr.<region>.amazonaws.com/memory-recall:latest
docker push <account-id>.dkr.ecr.<region>.amazonaws.com/memory-recall:latest

# 3. 创建 RDS 实例
aws rds create-db-instance \
  --db-instance-identifier memory-recall \
  --db-instance-class db.t3.medium \
  --engine postgres \
  --engine-version 14 \
  --master-username memory_recall \
  --master-user-password password \
  --allocated-storage 20

# 4. 部署 ECS 服务
aws ecs create-cluster --cluster-name memory-recall-cluster
# ... 配置任务定义和服务
```

#### 4.2 阿里云部署

**架构**：
- **ECS**：运行应用
- **RDS PostgreSQL**：数据库
- **Redis**：缓存
- **OSS**：存储图片和附件
- **SLB**：负载均衡

---

## 性能优化

### 1. 数据库优化

```sql
-- 1. 索引优化
CREATE INDEX CONCURRENTLY idx_memories_time_value ON memories(time_value);
CREATE INDEX CONCURRENTLY idx_memories_created_at ON memories(created_at DESC);

-- 2. 分区表（大量数据时）
CREATE TABLE memories_2026_q1 PARTITION OF memories
    FOR VALUES FROM ('2026-01-01') TO ('2026-04-01');

-- 3. 查询优化
EXPLAIN ANALYZE SELECT * FROM memories WHERE time_value >= '2026-03-01';
```

### 2. 缓存策略

```python
# Redis 缓存
from redis import Redis
import json

class CacheManager:
    def __init__(self, redis_url: str):
        self.redis = Redis.from_url(redis_url)
    
    def get_memory(self, memory_id: str) -> dict:
        """获取缓存"""
        cached = self.redis.get(f"memory:{memory_id}")
        if cached:
            return json.loads(cached)
        return None
    
    def set_memory(self, memory_id: str, memory: dict, ttl: int = 3600):
        """设置缓存"""
        self.redis.setex(
            f"memory:{memory_id}",
            ttl,
            json.dumps(memory)
        )
    
    def invalidate_memory(self, memory_id: str):
        """失效缓存"""
        self.redis.delete(f"memory:{memory_id}")
```

### 3. 异步处理

```python
# Celery 任务
from celery import Celery

app = Celery('memory_recall', broker='redis://localhost:6379/0')

@app.task
def process_image_async(image_path: str):
    """异步处理图片"""
    # OCR
    ocr_result = ocr_processor.process(image_path)
    
    # 人脸检测
    faces = face_detector.detect(image_path)
    
    # 结构化提取
    extracted = llm_service.extract_from_image({
        'ocr': ocr_result,
        'faces': faces
    })
    
    # 存储记忆
    memory_store.create(extracted)
```

---

## 监控与日志

### 1. 监控指标

```python
from prometheus_client import Counter, Histogram, Gauge

# 请求计数
request_count = Counter(
    'memory_recall_requests_total',
    'Total requests',
    ['method', 'endpoint', 'status']
)

# 响应时间
response_time = Histogram(
    'memory_recall_response_time_seconds',
    'Response time',
    ['method', 'endpoint']
)

# 记忆总数
memory_total = Gauge(
    'memory_recall_memories_total',
    'Total memories'
)

# 召回延迟
recall_latency = Histogram(
    'memory_recall_recall_latency_seconds',
    'Recall latency'
)
```

### 2. 日志配置

```python
import logging
from logging.handlers import RotatingFileHandler

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        RotatingFileHandler(
            'logs/memory_recall.log',
            maxBytes=10*1024*1024,  # 10MB
            backupCount=5
        ),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)
```

---

## 测试策略

### 1. 单元测试

```python
import pytest
from src.services.memory_service import MemoryService
from src.models.memory import MemoryCreate

@pytest.fixture
def memory_service():
    return MemoryService(db_connection)

def test_create_memory(memory_service):
    """测试创建记忆"""
    memory_data = MemoryCreate(
        content="测试内容",
        input_type="text"
    )
    
    memory_id = memory_service.create(memory_data)
    
    assert memory_id is not None
    assert memory_id.startswith("mem_")
```

### 2. 集成测试

```python
from fastapi.testclient import TestClient
from src.main import app

client = TestClient(app)

def test_create_memory_api():
    """测试创建记忆 API"""
    response = client.post(
        "/api/v1/memories",
        json={
            "content": "测试内容",
            "input_type": "text"
        }
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data['code'] == 200
    assert 'id' in data['data']
```

### 3. 性能测试

```python
import time
from locust import HttpUser, task, between

class MemoryRecallUser(HttpUser):
    wait_time = between(1, 3)
    
    @task
    def create_memory(self):
        self.client.post(
            "/api/v1/input/text",
            json={"content": "测试内容"}
        )
    
    @task
    def recall_memory(self):
        self.client.post(
            "/api/v1/recall/query",
            json={"query": "测试查询"}
        )
```

---

## 发布清单

### 发布前检查

- [ ] 所有测试通过
- [ ] 代码审查完成
- [ ] 文档更新
- [ ] 性能测试通过
- [ ] 安全检查通过
- [ ] 备份完成
- [ ] 回滚方案准备

### 发布步骤

1. **准备阶段**
   - 创建发布分支
   - 更新版本号
   - 更新 CHANGELOG

2. **测试阶段**
   - 运行完整测试套件
   - 执行性能测试
   - 执行安全扫描

3. **部署阶段**
   - 备份数据库
   - 执行数据库迁移
   - 部署新版本
   - 验证部署结果

4. **监控阶段**
   - 监控错误日志
   - 监控性能指标
   - 监控用户反馈

---

*文档版本：v0.1*  
*最后更新：2026-03-19*  
*维护者：颓弟*
