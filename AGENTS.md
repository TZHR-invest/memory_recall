# AGENTS.md

Memory Recall (v5.2.1) — 个人记忆与召回系统。FastAPI 后端（`apps/api/`），PostgreSQL + pgvector 存储，
火山引擎 doubao（OpenAI 兼容）LLM/embedding，客户端插件在 `apps/api/src/plugins/`。
仓库注释与 commit 多为中文 —— 与所改文件语言保持一致。

## 关键约束（改动前必读，勿破坏）

- **必须从 `apps/api/` 启动/运行**：代码使用绝对 `src.*` 导入，绝不能从仓库根起服务；
  macOS 系统 Python 3.9 过旧，需建 venv。
- **无迁移框架**：`apps/api/schema.sql` 是唯一事实源；改 schema 后重跑 `setup_database.py`（全量）
  或 `init_db.py`（仅建表）。
- **`VOLC_API_KEY` 必需**：缺失时记忆创建（embedding）、实体提取、关系检测全部失败。
- **Auth**：所有端点要求 `X-API-Key`（`rk_live_...` / `rk_test_...`）；`verify_container_ownership`
  允许精确匹配或 `{key_id}_*` 前缀（项目隔离）。Key 通过 `POST /auth/api-keys`（admin key）或 `install.py` 创建。
- **循环导入是故意的**：`profile_service` / `relation_service` 顶层 import `memory_store`，所以
  `memory_store` 只能在函数内（`process_memory_async` / `create_derived_memory`）惰性 import 它们 ——
  别"修"成顶层导入，启动即崩。
- **两种"取代"语义并存（勿混淆/勿"修复"）**：① 自动关系检测降级 `is_latest=FALSE` 但**不建版本链**（N:1 取代）；
  ② 显式 `POST /memories/{id}/update` 建完整版本链（1:1 修订）。由此积累的"孤儿旧版本"
  （`is_latest=FALSE, version=1, root_memory_id=NULL`）是设计产物不是数据损坏；
  真实历史走 `relation_service.get_version_history`。详见 [docs/ENTITY_DESIGN.md](docs/ENTITY_DESIGN.md)。
- **死代码勿挖**：`src/models/`、`src/services/{prompts,embedding_cache}.py` 不当功能来源。

## 快速启动

```bash
cd apps/api
python3 -m venv venv && venv/bin/pip install -r requirements.txt   # 首次
venv/bin/python setup_database.py                                   # 首次：建库 + pgvector + schema
venv/bin/python -m uvicorn main:app --reload --port 8000
```

## 文档索引（按需查阅）

| 主题 | 文档 |
|------|------|
| 安装 / 配置 / 部署 / 运维 | [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) |
| 架构与模块地图（惰性导入模式、死代码清单） | [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) |
| 测试（三层分级、环境注意点、常用命令） | [docs/TESTING.md](docs/TESTING.md) |
| 客户端插件（opencode / deepseek-tui / hermes） | [docs/PLUGINS.md](docs/PLUGINS.md) |
| 外部调研工作流（Human-in-the-Loop Research） | [docs/RESEARCH_GUIDE.md](docs/RESEARCH_GUIDE.md) |

## 文档沉淀规范（Docs-as-Records，强制）

**所有工作信息必须落成文档，禁止只存在于对话里。** 完整规范（目录分工、ADR/notes/designs 规则、收尾 checklist）
见 [docs/DOCUMENTATION_GUIDE.md](docs/DOCUMENTATION_GUIDE.md)。要点：

- 任务开始前先查 [docs/ISSUES.md](docs/ISSUES.md)（MR-xxx），避免重复劳动；
- 每次任务收尾更新 [docs/STATUS.md](docs/STATUS.md)（下一步不该只存在于对话里）；
- 修改文档后更新 [docs/README.md](docs/README.md) 索引；commit 时文档与代码一起提交（`docs:` 前缀）。
