# memory_recall 项目索引

**项目状态**: 开发中
**最后更新**: 2026-03-20

---

## 项目概述

个人记忆管理与召回系统，基于向量检索和知识图谱增强。

### 技术栈

- **后端**: FastAPI + PostgreSQL + pgvector
- **AI 服务**: 火山引擎（Embedding + LLM）
- **前端**: React + TypeScript

---

## 核心功能

| 功能 | 状态 | 说明 |
|------|------|------|
| 文本记忆创建 | ✅ | 支持短文本和长文本自动分段 |
| 文件上传 | ✅ | 支持 txt/md/log 文件 |
| 向量召回 | ✅ | 语义搜索 |
| 关键词召回 | ✅ | 基于分词的关键词匹配 |
| 图谱召回 | ⚠️ | 存在 SQL 列名错误 |
| 混合召回 | ✅ | 向量 + 关键词 + 图谱三路召回 |
| 自然语言召回 | ✅ | LLM 生成回答 |

---

## 项目结构

```
memory_recall/
├── apps/
│   └── api/           # FastAPI 后端服务
├── packages/          # 共享包
├── web/               # React 前端
├── config/            # 配置文件
├── scripts/           # 测试脚本
├── docs/              # 文档
├── reflection/        # 反思报告
├── migrations/        # 数据库迁移
└── storage/           # 文件存储
```

---

## 测试记录

### 2026-03-20 完整测试

- **报告**: `docs/COMPREHENSIVE_TEST_REPORT_COMPLETE.md`
- **反思**: `reflection/2026-03-20-1833-项目测试-memory_recall完整测试.md`
- **通过率**: 81%（17/21）
- **主要问题**:
  1. API 超时（图谱构建、并发请求）
  2. SQL 列名错误（`m.user_id` 应为 `e.user_id`）

---

## 已知问题

| 问题 | 优先级 | 状态 |
|------|--------|------|
| 图谱召回 SQL 列名错误 | 高 | 待修复 |
| API 超时（30s 不够） | 高 | 待修复 |
| 并发请求处理慢 | 中 | 待优化 |

---

## 快速启动

```bash
# 启动 API 服务
cd apps/api
source venv/bin/activate
python -m uvicorn main:app --host 127.0.0.1 --port 8000

# 测试
curl http://localhost:8000/health
```

---

## 相关文档

- [设计文档](DESIGN.md)
- [进度跟踪](PROGRESS.md)
- [API 文档](http://localhost:8000/docs)（服务启动后）