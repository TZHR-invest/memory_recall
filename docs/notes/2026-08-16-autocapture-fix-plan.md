# 自动捕获膨胀修复 · 可执行实施计划（2026-08-16）

> 状态: **阶段 A+B 已实施完成（2026-08-16）**，待部署验证；阶段 C/D 待观测后执行
> 前置分析：[2026-08-16-autocapture-bloat-analysis.md](2026-08-16-autocapture-bloat-analysis.md)（数据事实与方案 v2）
> 本文件是 v2 方案的落地版：每个改动精确到文件/函数/参数，含测试、部署、回退与验收标准。

## 0. 总览

| 阶段 | 内容 | 风险 | 生效范围 |
|------|------|------|---------|
| A | dsh 插件侧：上限对齐 + 门槛提高 + 会话节流 + 来源标记 | 低（配置可回退） | dsh 插件 |
| B | 后端：/extract-memory 去重 + 异步写入兜底 | 低-中（fail-open + 阈值可配） | 所有插件 |
| C | prompt 排除"一次性任务细节" | 低（观测后调） | 所有插件 |
| D | static 纪律审计（一次性数据操作） | 低（先确认可回滚） | 存量数据 |

执行顺序：A → B → 验证 → 观测 3~5 天 → C → D。A、B 可同日完成。

## 阶段 A：dsh 插件侧（4 个文件 + 测试 + 部署）

### A1. 批上限对齐（1 行）

- 文件：`apps/api/src/plugins/dsh/capture.js` 第 29 行
- 改动：`extracted.memories.slice(0, 10)` → `slice(0, 5)`（与蒸馏 prompt"最多 5 条"一致）
- 验证：该分支仅 extract 模式生效；配合 A4 的日志可观测实际写入条数

### A2. 提高捕获门槛（1 行）

- 文件：`apps/api/src/plugins/dsh/config.js` 第 66 行 DEFAULTS
- 改动：`captureMinLength: 40` → `captureMinLength: 100`（短轮不再触发蒸馏；
  依据：08-15 凌晨大量批次每批仅 1~2 条，说明 40 字符门槛偏低）
- 回退：config 写回 40 即恢复

### A3. 会话级节流 + 摘要累计

- 文件：`apps/api/src/plugins/dsh/capture.js`
- 新增配置：`captureMinIntervalMs`（默认 600000ms=10 分钟；0 = 关闭节流）
  - `config.js` DEFAULTS 加 `captureMinIntervalMs: 600000`；resolveConfig 加
    `captureMinIntervalMs: clampInt(raw.captureMinIntervalMs, 0, 3600000, DEFAULTS.captureMinIntervalMs)`
  - `index.js` Config schema 加 `captureMinIntervalMs: z.number()`
  - `README.md` 配置表加一行
- 逻辑改动（createCaptureHandler 内）：
  1. 闭包新增两个 WeakMap：`lastCaptureAt`（session → 上次蒸馏时间戳）、
     `pendingSummary`（session → 节流窗口内累计的摘要文本）；
  2. capture 函数签名改为直接接收组装好的 summary 字符串（调用处负责 buildSessionSummary），
     内部不再自行组装（累计摘要需要调用处合并）；
  3. turn/end 分支（现 85~92 行）逻辑改为：
     a. assistantText < captureMinLength → 跳过（现状保留）；
     b. `now - lastCaptureAt < captureMinIntervalMs` → 本轮摘要追加进 pendingSummary
        （超 captureMaxChars 截尾），不触发蒸馏；
     c. 否则 → 蒸馏 `pendingSummary + 本轮摘要`，清空 pending，更新 lastCaptureAt。
- 信息不丢保障：节流只是"暂缓入长期记忆库"，对话原文完整保留在 session 事件流；
  累计窗口让被推迟的信息在窗口结束后仍进入蒸馏。

### A4. 捕获来源标记（供阶段 B 后端识别）

- 文件：`apps/api/src/plugins/dsh/capture.js`（31~35 行 addMemory 调用）
- 改动：options 加 `metadata: { _capture: true }`
- 文件：`apps/api/src/plugins/dsh/client-lib.js`（114~128 行 addMemory）
- 改动：`const metadata = { ...(type ? { type } : {}), ...(options.metadata || {}) };`

### A 阶段测试

- `apps/api/src/plugins/dsh/test/harness.test.js` 新增（均连真实后端，沿用现有 capture-test 容器模式）：
  1. "自动捕获：节流窗口内不重复落库"——config 设 captureMinIntervalMs=60000，连续两次 turn
     （间隔 <1s），断言容器内仅 1 条捕获（第二次被节流）；
  2. "自动捕获：节流后摘要累计蒸馏"——第一次 turn 被节流（interval 设很大），第二次 turn 后
     断言落库内容同时包含两次的 marker（raw 模式，确定性断言）。
- 回归：`node --test test/`（或仓库约定命令）全量通过

### A 阶段部署与回退

- 构建：`bun run build`（若 cp -r 报 illegal option，按既有经验手动补 dist/i18n）；`node --check` 产物
- 重启：**用户在终端执行 `bash install.sh --restart`**（防崩纪律：agent 不自杀式重启宿主）；
  冒烟失败自动中止
- 回退：配置 `captureMinIntervalMs: 0` + `captureMinLength: 40` 即恢复原行为（无需重建 bundle），
  或 git revert + 重建

## 阶段 B：后端去重（3 个文件 + 测试 + 部署）

### B1. /extract-memory 结果去重

- 文件：`apps/api/src/api/memories.py`（extract_memory_from_summary，1146~1159 行之间）
- 改动：
  1. `ExtractMemoryResponse` 增加字段：`dropped: List[Dict[str, str]] = Field(default_factory=list)`；
  2. memories 列表构造后、return 前插入过滤（每条候选一次向量检索，同容器 top-1）：
     ```python
     kept, dropped = [], []
     for m in memories:
         try:
             similar = await memory_store._check_similar_memory(
                 m.content, container_tag, threshold=settings.CAPTURE_DEDUP_THRESHOLD,
             )
         except Exception:
             similar = None  # fail-open：检索异常不阻断蒸馏
         if similar:
             dropped.append({
                 "content": m.content,
                 "reason": f"与已有记忆相似 {similar['similarity']:.3f}: {similar['content'][:50]}",
             })
         else:
             kept.append(m)
     return ExtractMemoryResponse(memories=kept, has_worthwhile=len(kept) > 0, dropped=dropped)
     ```
  3. 端点内已有 `container_tag`（Depends require_permission 注入）与 `memory_store`（顶部已 import），
     无需新增依赖。
- 成本说明：每条候选多一次 embedding（_check_similar_memory 内部生成）——候选落库后本来也要
  异步算 embedding（asyncProcess=true），被丢弃条目的 embedding 净省；整体成本不增反减。

### B2. 异步写入兜底（_capture 标记走 0.85 阈值）

- 文件：`apps/api/src/services/core/memory_store.py`（process_embedding_async，299~322 行）
- 改动（替换现有固定阈值 merge 分支）：
  ```python
  meta = memory.metadata or {}
  is_capture = bool(meta.get("_capture"))
  threshold = (
      settings.CAPTURE_DEDUP_THRESHOLD if is_capture
      else settings.MEMORY_MERGE_THRESHOLD,
  )
  similar = await self._check_similar_memory(
      memory.content, memory.container_tag,
      threshold=threshold, embedding=embedding, exclude_id=memory_id,
  )
  if similar:
      if is_capture:
          # 捕获来源重复：物理丢弃新行（此时实体/关系未提取，无关联数据）
          await db.execute("DELETE FROM memories WHERE id = $1", memory_id)
          _logger.info(f"Capture memory {memory_id} dropped (dup of {similar['id']} sim={similar['similarity']:.3f})")
      else:
          await self.merge_similar_memory(similar["id"], memory.content)
      return
  ```
  （现有 merge 后 "_status 清理" 逻辑在丢弃路径不需要；保留路径维持现状）
- 文件：`apps/api/src/config.py` 新增 `CAPTURE_DEDUP_THRESHOLD: float = 0.85`
- POST /memories 无需改（metadata 已透传存库，_capture 随 JSONB 落库）

### B 阶段测试

- 后端测试（按 TESTING.md 三层分级，连真实 DB）新增：
  1. extract 去重：patch LLM 返回 2 条（1 条与容器已有记忆 embedding ≥0.85 近似）→
     响应 memories=1、dropped=1，且 dropped 带 reason；
  2. extract 去重 fail-open：patch _check_similar_memory 抛异常 → memories 原样返回；
  3. process_embedding_async 捕获丢弃：先插一条基准记忆 + 一条 _capture 近似记忆 →
     处理后 _capture 行被物理删除；
  4. process_embedding_async 显式写入维持 0.95：非 _capture 近似记忆不被删（回归现状）。
- 全量 pytest 回归（现有 78+ 测试全绿）

### B 阶段部署与回退

- 部署：`docker compose restart api`（或确认后执行）；`/health` + 手工 curl /extract-memory
  （提交与库中已有记忆重复的 summary → 响应 dropped 非空）验证
- 回退：`CAPTURE_DEDUP_THRESHOLD=0.95` 即恢复原行为（无需重启，settings 读取时机确认）或 git revert

## 阶段 C：prompt 排除"一次性任务细节"（观测后）

- 文件：`apps/api/src/api/memories.py`（中文 prompt 1059~1063 行 / 英文 prompt 1106~1110 行）
- 中文新增硬性排除第 5 类：
  "5. 一次性任务细节：任务完成后即失效的操作细节（排障步骤/临时地址/一次性验证命令）；
  但长期有效的连接信息/配置/规则保留（如\"某服务长期地址是X\"）"
- 触发条件：阶段 A+B 落地并观测 3~5 天后，若写入量仍 >100/天或 dropped 占比过高再调；
  避免与 B1 检索去重叠加导致双重过滤难归因

## 阶段 D：static 纪律审计（一次性，先确认后执行）

1. 生成清单：
   ```sql
   SELECT id, container_tag, left(content, 60) AS content FROM memories
   WHERE is_latest=TRUE AND is_forgotten=FALSE AND is_static=TRUE
     AND COALESCE(metadata->>'type','') != 'preference';
   ```
2. 与用户确认清单 → 执行 `UPDATE memories SET is_static=FALSE WHERE id IN (...)`；
3. 回滚：清单已存档，反向 UPDATE 即可；
4. 写入路径约束：memory_store 工具 / opencode 插件核对"仅 preference 可 static"（capture.js 已符合）。

## 验收标准（A+B 落地后 3~5 天）

| 指标 | 基线（08-15） | 目标 | 数据来源 |
|------|--------------|------|---------|
| 单日写入量 | 518 | ≤100 | /stats/timeline |
| >5 条/批 的批次 | 10 批 | 0 | 按分钟聚类 SQL |
| 同日近似对（≥0.80） | 52 对 | ≤5 | embedding 自连接 SQL |
| extract dropped 条数 | 未统计 | 记录基线 | extract-memory 响应 |
| 非 preference static | 216 条 | 0（D 阶段后） | SQL |
| embedding 调用（memory 类） | 717/天 | ≤300/天 | recall_embedding_logs |

## 风险与对策

| 风险 | 对策 |
|------|------|
| 节流失真（长会话信息延迟） | 摘要累计窗口 + 信息本就在 session 事件流 |
| 去重误杀（有价值记忆被拦） | 阈值 0.80 可配；捕获路径误丢代价低（对话在 session 事件流）；dropped 全量审计可见；fail-open 不阻断 |
| 并发竞态（多会话同时写） | B2 异步兜底（0.85 + DELETE） |
| 物理删除不可逆 | 仅删"未提取实体、从未被消费"的重复新行；显式写入永不走此路径 |
| dsh 插件改坏宿主 | 防崩纪律：bundle 重建 + node --check + harness 冒烟 + 用户终端重启 |
| 观测期不足调参 | 3~5 天窗口，基线已存档，避免盲调（既有教训） |

## 7. 实施记录（2026-08-16）

阶段 A+B 全部完成，测试与真实验证通过：

| 项 | 结果 |
|----|------|
| A1~A4 | capture.js（slice 5 + 节流 + 累计 + _capture）、config.js（门槛 100 + captureMinIntervalMs 600000）、index.js schema、client-lib.js（metadata 合并 + extractMemory containerTag）、README；bundle 重建（client.js 9044 字节） |
| B1 | /extract-memory 去重：dropped 审计字段 + 0.80 阈值 + **container_tag 对齐修复**（初版未传容器 tag，检索落在主容器导致项目容器内近似记忆检索不到——HTTP 实测发现后修复，插件落库容器与检索容器同域） |
| B2 | process_embedding_async 按 _capture 选阈值：捕获 0.80 物理 DELETE / 显式 0.95 merge 不变 |
| 阈值校准 | 实测同主题碎片（同一地址两条变体）embedding 相似度 0.81，0.85 拦不住 → 定 0.80 |
| **额外根因修复** | CHINESE_STATIC_INDICATORS 裸"是"指标：任何含"是"的陈述句（"服务地址是X"）被 fallback 检测判 static，且 LLM 提取的 is_static 会覆盖写入参数（memory_store.py:171-189/373-446）——08-15 那 216 条非 preference static 的真正机制；已移除裸"是"（保留"职业是/工作是"等复合词），新增回归测试 |
| 测试 | dsh 26/26（含节流 + 累计 2 个新测试）；后端 test_capture_dedup 8 个 + test_detect_is_static 12 个全绿；全量 424 通过（3 失败 = MR-024 已知测试连接冲突，单独跑通过） |
| 真实链路验证 | 带 container_tag 调 /extract-memory：与基准记忆相似度 0.813 的候选被 dropped（附 reason），基准保留 |
| 后端部署 | docker compose restart api 已执行，health OK；代码 bind mount 即时生效 |

### 待办
- [ ] 用户终端执行 dsh 插件部署：`cd apps/api/src/plugins/dsh && bash install.sh --restart`（防崩纪律）
- [ ] 部署后观测 3~5 天（§5 指标），再决定阶段 C（prompt 排除一次性任务细节）与 D（static 存量审计——注意：存量 216 条 static 的成因已修正，是否降级可再评估）

## 8. 观测评估（2026-08-18，优化后第 2~3 天）

数据窗口：08-16 02:00 UTC 起（重启生效后）共 317 条写入。

| 指标 | 08-15 基线 | 优化后 | 目标 | 判定 |
|------|-----------|--------|------|------|
| 单日写入 | 498 | 08-16 76 / 08-17 115 / 08-18 126（10:38 前） | ≤100 | ⚠️ 重活日仍 100+ |
| >5 条/批 | 10 批 | 2 批（3 天内） | 0 | ✅ 基本消除 |
| 同日近似对 ≥0.80 | 52 对 | 17 对 | ≤5 | ⚠️ 下降 67% |
| capture 内部近似对 ≥0.85 | —（旧全漏） | 1 对 | ~0 | ✅ capture 去重成功 |
| agent 显式写内部近似对 ≥0.85 | — | 5 对（约 22% agent 写冗余） | — | ⚠️ 新发现 |
| static 非 preference | 216 条 | 139 条/317（44%，多为长期规则，语义合理） | — | ✅ 内容合理 |

结论：
- **capture 路径优化完全成功**：内部冗余 ~0、批次超限消除、容量降 75%（498→~120）。
- **剩余冗余主要来自 agent 显式写入**（memory_store 工具）：热点研究同分钟连写 3 条（0.90+）、
  "agent 不能重启宿主"同规则跨会话重复。这些不走 0.80 去重（仅 _capture 走），0.95 阈值不拦。
- **跨容器同规则重复**（同一规则写在不同 project 容器）是项目隔离的设计产物，非缺陷。
- 绝对量 100+ 主要受重活日驱动（08-18 凌晨 opencodex 模型迁移写了 79 条高质量经验），
  内容质量抽查为真实高价值经验，非碎片。

可选后续（待用户拍板）：
- agent 显式写入轻量去重：POST /memories 对无 _capture 写入用较高阈值（如 0.90）查同容器，
  命中时仍落库但响应附"近似重复提示"（不丢弃，避免误删有意保存）；或严格模式丢弃。
- 不建议再压 capture：重活日经验密度高，过度节流会丢信息。

## 9. 存量数据评估（2026-08-18，决定：不主动整理）

- 存量全貌：2678 条有效 / 21 容器（全真实项目，无测试残留）；static 637 / dynamic 2041；
  旧版本 1459（设计产物不动）、forgotten 88（已软删）、无 embedding 0（健康）。
- 冗余：0.85+ 近似对 85 对（3%）；≥0.95 真重复仅 6 对 12 条（0.4%），全部同容器同天写入
  （04-15/07-01/07-27/08-14），历史重复无召回收益。
- 低价值：conversation 248 条中仅 1 条 raw 流水账（"你只发了一个1"），极少无害。
- 内容质量：热点研究 / 排障经验 / 运营记录（hermes 1162 条）为主，高价值。
- **决定：不主动整理**。理由：① 真重复 0.4% 清理收益≈0；② 0.85-0.95 区间的"重复"多为
  信息互补版本，机械删除有信息损失风险（merge 机制因同样原因被否）；③ 写入侧已由
  _capture 0.80 去重机制约束，存量冗余是历史遗留且无害；④ 符合项目"避免过度设计"文化。
- 唯一有意义的清理场景：某项目容器废弃时按容器整清（当前 21 容器均在用，无此需求）。

## 10. 用户画像净化（2026-08-18，已实施）

问题：用户容器 static 43 条 / 11KB，注入占 context 69-98%（实测），混入项目性内容（漫剧制作、dsh-vision、WSL、热点研究等）。

方案演进（用户两轮纠正后定稿）：
- 画像定位 = "每个项目/每个会话都必须知道的核心特征"（无条件注入），非"长期事实"
- 漫剧制作/EmQuantAPI 等是**场景特定偏好**，只在相关任务时需要 → 向量召回，不常驻画像
- LLM 分类（9 画像/34 非画像）实测 8/8 准，但纯 LLM 有漂移风险 → 规则兜底

实施：
1. 存量 43 条写 metadata.profile_worthy（9 true / 34 false，回滚清单 docs/notes/profile-purify-rollback-20260818.json）
2. _build_profile 过滤：profile_worthy=false 退出画像缓存；无标记默认 preference 进/非 preference 不进
   （防热点研究等新 static 无标记混入——实测发现后修正）
3. memory_store 工具加提示：scope=user+isStatic+type≠preference 时提醒
4. 测试：_build_profile 过滤（true 保留/false 过滤/无标记 preference 保留/无标记非 preference 排除）

验证（实测 context-inject）：static 43→9 条、注入字符 11239→2687（-76%）；9 条核心画像全保留；
热点研究/MR-025 为 dynamic（最近活动，设计行为）；漫剧制作/dsh-vision/WSL 退出画像但可向量召回。

不动项：is_static 保持（LLM 覆盖不复活画像，profile_worthy 独立维度）；注入机制（永不截断锁定设计）；
dynamic 注入（时效即价值）。

## 11. 画像写入侧优化（2026-08-18，已实施）

漏洞：新写入的 static（async 路径）无 profile_worthy 标记，注入层默认 True → 混入画像。

修复：写入侧自动标记（轻量规则方案，非 LLM prompt）：
- process_memory_async + create 同步路径：is_static 时补 meta["profile_worthy"]，
  规则 = preference/无 type → true（用户偏好进画像），其他类型 → false（不进画像可召回）
- 已有显式标记不覆盖（保护存量 9 true / 34 false）
- 端到端验证：async 写 learned-pattern static → profile_worthy=false，注入 0 命中

选型理由（轻量规则 vs LLM prompt）：
- 同步路径已有 LLM is_static 覆盖过滤（LLM 判非静态→is_static=false→不进画像）
- 异步路径规则可拦绝大部分混入（热点研究/项目配置/临时经验都是 learned-pattern 等）
- npm 2FA 类"技术类型但跨项目"极少数误判 false → 仍可向量召回，不丢知识
- 零额外 LLM 成本、一处改动、低风险，符合避免过度设计
