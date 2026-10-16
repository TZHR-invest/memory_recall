# 2026-10-16: LLM 上游欠费 12 天静默事故 —— 实体/关系抽取与自动捕获双双降级而无人发现

> 类型: 事故复盘 + 修复记录（含可观测性补强）
> 日期: 2026-10-16
> 参与: 用户（发现 + 拍板处置）/ ai-agent(206) 侧 agent
> 关联: [DEPLOYMENT.md §故障排查](../DEPLOYMENT.md) · [ARCHITECTURE.md 终态契约](../ARCHITECTURE.md) ·
> 落地 commit（模型切换 + 降级标记 + 探针 + 回填脚本）· 历史同类静默：2026-09-22 零实体归因笔记

## TL;DR

用户的疑问是"dsh 自动提取记忆、实体和关系提取是不是都坏了？是不是模型不能工作？为什么没发现？"
**三问全中，但原因不是模型**：opencodex 代理下 `commandcode` 这个上游账号自 **2026-10-04 13:36**
起额度耗尽（每次调用 `HTTP 400 Provider error 400: You have insufficient credits`），
于是三条 LLM 依赖链路**同时降级且全静默**，持续 **12 天**无人发现：

| 链路 | 降级后的行为 | 实测损伤 |
|---|---|---|
| 实体/关系抽取 | `_fallback_extract_with_relations()` 退规则抽取，`relations: []` **写死为空** | 实体/天 201~685 → **11~27**；`entity_relations` 除 10-04、10-13 外**全为 0**；10-04 起 198 条最新记忆里 **111 条（56%）零实体** |
| dsh 自动捕获蒸馏 | `/extract-memory` 把异常 `except` 成 `200 + has_worthwhile:false` ⇒ 插件判定"无值得保存" **不落库** | `_capture=true`：09-27~09-30 为 65/114/26/117 条/天 → **10-05 起 0**（仅 10-13 有 17） |
| 记忆关系自动检测 | `_fallback_batch_detection()` 退关键词标记判定（conf 0.5~0.7） | 每天仍有 30~80 条 `updates`，但质量退化为启发式 |

同一事故在 **09-23 13:28~09-24**（`429 weekly usage limit`，372 次）已发生过一次，导致
09-24/25/26 三天捕获为 0 —— 同样没人发现。**这是系统性盲点，不是偶发。**

## 证据链（可复算）

```
# 1) 调用状态码按天（api 容器日志）
grep -oE '2026-[0-9-]+ [0-9:,]+ httpx: HTTP Request: POST .*chat/completions "HTTP/1.1 [0-9]+' \
  | 汇总：≤10-03 全 200；10-04 起 400 成常态（10-04:42 … 10-16:76，累计 952 次）
        唯一例外：10-13 15:10–17:59 有 41 次 200（额度短暂恢复 ≈2.8h）

# 2) 400 的报文只有一种（375 条降级日志全指向它）
Provider error 400: You have insufficient credits to make this request. Please purchase more credits...

# 3) 断点精确定位
10-04 13:23:28 最后一批 200 → 10-04 13:36:00 首个 400

# 4) 落库侧的对应变化
实体/天：09-30~10-03 有 201~685；10-05 起 11~27
entity_relations：10-04=182、10-13=67，其余日期 0
_capture=true：10-05 起 0（除 10-13=17）
降级 WARNING：10-04 起 377 条（10-05 起 ≈ 1 条/写入，即**每次写入都降级**）

# 5) 现网实测（事发当天 11:57）
POST /v1/chat/completions model=commandcode/deepseek/deepseek-v4.1-flash → 400 insufficient credits
POST /v1/chat/completions model=opencode-go/deepseek-v4.1-flash   → 200（1.6s）
POST ark.cn-beijing.volces.com (doubao-seed-2-0-mini)             → 200
```

**模型是好的**（同代理换线路即可用），坏的是上游账号余额。

## 为什么 12 天没人发现（五条结构性原因）

1. **失败被设计成"正常结果"**：抽取失败退规则、捕获失败返回"无值得保存"。客户端拿到的是 200，
   没有任何一处报错。
2. **状态字段不反映降级**：记忆照样 `_status=completed` ⇒ 看板 `anomalies.processing/failed/
   processing_stuck` **全是 0**（事故期间全库绿灯）。
3. **LLM 没有遥测**：库里没有 `llm_call_logs` 表（设计稿 [llm-call-logging.md](../../initiatives/crystal/llm-call-logging.md)
   一直"待实现"），看板也没有 LLM 成功率/抽取质量卡片。**对照组**：embedding 失败会写
   `recall_embedding_logs.ok=false`，所以 2026-10-16 那 28 次 DNS 失败看板立刻可见 ——
   这个不对称正是"DNS 看得见、欠费看不见"的原因。
4. **插件无法区分"确实无价值"与"链路故障"**：raw 回退只在**抛错**时触发，而接口返回的是 200+空。
5. **降级是渐进的且被掩盖**：向量召回照常工作，只有图谱通道慢慢空掉、捕获悄悄归零，
   看起来像"最近没什么值得记的"。同类 429 事故已静默过一次，说明靠人盯日志不成立。

## 处置（本次落地）

| 项 | 内容 | 验证 |
|---|---|---|
| 止血 | `OPENCODEX_LLM_MODEL`：`commandcode/deepseek/deepseek-v4.1-flash` → `opencode-go/deepseek-v4.1-flash`（`.env`/`.env.example`/`docker-compose.yml`/`config.py` 四处同步），`docker compose up -d api` | 写入一条测试记忆 → 抽到 5 个类型精确实体（config/service/version/software）；第二条 → 4 实体 + 6 条 `entity_relations` 落库 |
| 降级可见 | `llm_entity_extraction` 每条降级路径带原因（`no_llm_client`/`llm_timeout`/`llm_parse_failed`/`llm_error: insufficient_credits\|rate_limited\|<Type>`），`process_memory_async` 落 `metadata._extraction_degraded`（成功则清除） | 契约写进 [ARCHITECTURE.md](../ARCHITECTURE.md) |
| 看板可见 | `stats/overview.anomalies.extraction_degraded_{24h,7d}` + dashboard 新卡片「抽取降级 (24h)」，>0 即标红 | 卡片取数同上 |
| 邮件告警 | 新增 `scripts/llm_health_probe.py`：①按 `.env` provider 发最小 chat 请求；②查近 60 分钟 `_extraction_degraded`；任一失败即故障。状态机：ok→fail 立即发信、持续失败每 6h 复提醒、fail→ok 发恢复信。`/etc/cron.d/memory-recall-llm-probe` 每 15 分钟跑（flock 防重叠） | 实测：`--test-mail` 收到；用欠费线路 `--model commandcode/...` → 收到 🔴 告警且复跑不重复；恢复正常线路 → 收到 🟢 恢复信 |
| 插件不再丢内容 | `/extract-memory` 降级时返回 `degraded=true + degraded_reason` 并打 WARNING；dsh 插件把 degraded 当故障 ⇒ 告警 + 回退 raw 捕获（`capture.js`） | dsh 插件测试 **29/29 全绿**（含联网捕获用例）；部署副本已同步，**待重启 dsh 生效** |
| 存量回填 | 新增 `scripts/backfill_entities.py`（默认 dry-run；按 `_extraction_degraded` 或"零实体"筛选；走线上同一 `extract_with_relations` + `_store_entity_graph` 写路径；幂等） | 候选 111 条；`--apply` 以 systemd 瞬态单元 `mr-backfill-entities` 脱离会话运行（见下"踩坑"） |
| 回归测试 | 新增 `tests/test_v2/test_extraction_degraded_marker.py`（4 用例）：降级 ⇒ 必须落 `_extraction_degraded` 且仍写 `completed`；正常 ⇒ 必须清除该键；规则兜底返回值自带原因；`insufficient credits` 归类为 `llm_error: insufficient_credits` | 4 passed；CI 快跑档 524 passed / 6 failed / 38 errors，失败与 MR-026 基线**逐项一致** |

## 复算/运维入口

```bash
# 体检（宿主机，cron 同款命令）
cd apps/api && python3 scripts/llm_health_probe.py --dry-run

# 换线路前预检候选（不写库、不发信）
python3 scripts/llm_health_probe.py --dry-run --model opencode-go/deepseek-v4.1-flash

# 存量回填（容器内跑，才有 DB/provider 环境）
docker exec -i memory_recall-api-1 python scripts/backfill_entities.py --dry-run
docker exec -i memory_recall-api-1 python scripts/backfill_entities.py --apply
```

## 落地过程中的两个坑（已写进 DEPLOYMENT）

1. **`docker compose up -d` 不会重建"配置未变化"的容器**：改完 `stats.py`/`memories.py` 后 `up -d`
   只输出 postgres Waiting/Healthy，容器 `StartedAt` 还是旧的 ⇒ 新字段查不到（本次先误判成
   "代码没生效"，实为进程没重启）。**判据**：`docker inspect -f '{{.State.StartedAt}}' memory_recall-api-1`
   与源文件 mtime 对比；要生效用 `docker compose restart api`。
2. **`docker exec` 跑的长任务会随服务重启被中断**：dsh web 重启（为生效插件副本）把本会话的
   进程树一起带走，回填脚本死在 38/111。改用
   `sudo systemd-run --unit=mr-backfill-entities --collect /usr/bin/docker exec memory_recall-api-1 python scripts/backfill_entities.py --apply`
   脱离会话运行（进度看 `journalctl -u mr-backfill-entities`）。

## 未做 / 待跟进

- `llm_call_logs` 表（调用级遥测）仍未实现：本次只做到"降级可判定 + 计数 + 告警"，
  还没有请求级成功率/延迟/成本面板。
- 记忆关系自动检测的降级（`_fallback_batch_detection`）只补了日志，没有落库标记；
  它的质量退化比实体抽取更难察觉（每天仍有几十条 `updates`）。
- 10-04~10-16 期间**未被捕获**的对话内容不会自动回来：库里没有原文，但 dsh 会话日志还在，
  必要时可离线重蒸馏（未排期）。
- 上游额度是外部依赖：本次选了同代理的 `opencode-go` 线路，仍在 opencodex 单点内；
  若需要彻底解耦，可评估切 `LLM_PROVIDER=volcengine`（doubao，实测 key 可用）或加多 provider 轮询。
