# LLM 换用 opencodex / commandcode deepseek-v4.1-flash

> 状态: DONE · 日期: 2026-09-22 · 影响面: 后端全链路 LLM（实体提取 / 关系检测 / 记忆蒸馏 / 画像判断 / crystal 拆条与碰撞）

## 决策与落地

把 `apps/api` 的 LLM 从火山方舟 `doubao-seed-2-0-mini-260215` 换成 **opencodex 代理上的
`commandcode/deepseek/deepseek-v4.1-flash`**；**embedding 不动**（仍 `doubao-embedding-vision-251215`，1024 维）。

- 新增第三个 provider 分支 `LLM_PROVIDER=opencodex`（`src/config.py` + `src/llm/client.py`），
  而不是复用 `deepseek` 分支——后者语义指"官方直连"，两把 key、两套 base 混用会误导后来人；
- `.env` / `.env.example` / `docker-compose.yml` 同步（`.env` 已备份 `.env.bak-opencodex-*`，
  并把 `.env.bak-*` 加进 `.gitignore`：备份含明文 key，不能入库）；
- 代码是 bind mount，改完**必须 `docker compose restart api`**（`up -d` 不会因挂载内容变化而重建）。

## 为什么不是直接改一行模型名（关键坑）

**思考型模型把思考链计入 `max_tokens`，调用方默认值不够 ⇒ content 返回空、实体提取静默丢结果。**
实测（换模型后第一次写记忆）：

```
LLM 请求: model=commandcode/deepseek/deepseek-v4.1-flash max_tokens=2000 prompt_len=2969
LLM 响应: ok=false content='' reasoning_len=7148 usage=2879 (reasoning=2000) elapsed=9.8s → 返回空
```

三连空（`2000` × 3 + 蒸馏路径 `1500` × 1）→ 该条记忆 **0 个实体**；记忆本身照常入库，
所以**不报错、只是悄悄退化**（与 2026-08-19 crystal 那次同源，见
[note](2026-08-19-reasoning-llm-max-tokens-empty-content.md)）。

**修法**：`src/llm/client.py` 的思考型 provider 下限 `REASONING_MIN_MAX_TOKENS` 由 `1000` 提到 **`8000`**
（`_min_max_tokens` 只抬高上限、不预扣费用）。实测该 prompt 需思考 ~2600 token；修后同一路径：

```
LLM 请求: model=commandcode/deepseek/deepseek-v4.1-flash max_tokens=8000 prompt_len=2969
LLM 响应: ok=true content_len=1331 reasoning_len=9519 usage=3953 (reasoning=2600) elapsed=13.7s
```

记忆写入实测思考量分布：**1174 / 2600 / 3628 / 4771 token**（prompt 2.4k–5.1k 字符），
`4000` 也够、`2000` 必空 —— 取 `8000` 留约 2× 余量（crystal 链路另有显式 `16000`）。

## 验证（2026-09-22，全部走真实 HTTP 链路，非 mock）

| 项 | 结果 |
|---|---|
| provider/model（运行实例） | `opencodex` / `commandcode/deepseek/deepseek-v4.1-flash`，base `http://192.168.0.206:10100/v1` |
| 写记忆 → 实体提取 | ✅ 一条记忆抽出 6 个实体（张三 / OpenCodeX / meshdeck / memory_recall / ai-agent 主机 / docker 容器） |
| 关系检测（第二条相关记忆触发） | ✅ 生成 `extends` 关系，confidence 0.9（修前该路径正是 `prompt_len=5121` 返空的那条） |
| 语义召回 `/context-inject` | ✅ 问句不复用正文词仍召回该条（1 条），`failed_channels=[]` |
| embedding 未受影响 | ✅ `recall_embedding_logs` 新增记录仍为 `doubao-embedding-vision-251215` / 1024 维 |
| 单元回归（快跑档） | ✅ **与换模型前逐项一致**：`6 failed / 474 passed / 15 skipped / 38 errors`（用 `LLM_PROVIDER=volcengine` 复跑同结果 ⇒ 全部为既有基线：crystal schema 未建 + 测试间 loop/顺序耦合） |

测试数据（`..._project-opencodex-verify-*` 两个容器：3 记忆 / 6 实体 / 1 关系 / 2 trace / 7 embedding 日志）**已全部清理**，复查残留为 0。

## 回退

`apps/api/.env` 里把 `LLM_PROVIDER` 改回 `volcengine`（或 `deepseek`）后 `docker compose restart api`
即可，代码分支与配置都保留；原 `.env` 备份在同目录 `.env.bak-opencodex-20260922-111904`（已 gitignore）。
`REASONING_MIN_MAX_TOKENS` 对非思考型 provider 不生效，无需回退。

## 遗留与观察

- **写入变慢**：带实体提取的记忆写入 **14–24 s**（doubao mini 时代约数秒）。dsh 插件写预算 90 s、
  读预算 30 s、`LLM_EXTRACTION_TIMEOUT=60 s`，都在预算内；但单条延迟的方差很大（实测 3.4–24.4 s），
  批量写入场景要留意。
- **思考链字段名不同**：opencodex 返回 `message.reasoning`（官方直连是 `reasoning_content`），
  `_response_summary` 已两者都读，否则排查日志会永远看到 `reasoning_len=0` 而误判。
- **`reasoning_effort=low` 已默认下发**（`aextract_json` 不接受该 kwarg，只能走客户端默认值），
  实测思考量 323→165 token（短 prompt）。
- **顺带发现（与本次改动无关）**：启动日志 `crystal 对账 worker 扫描失败: relation "crystal.evidence_processing"
  does not exist` —— 该库 **没有应用 `crystal` schema**（`information_schema.schemata` 查无），
  而 `schema.sql` 有定义；`tests/test_crystal/integration/` 的 38 个 error 同源。属既有缺口，未处理。
