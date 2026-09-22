# 实体抽取太稀：根因与修复（关系版 prompt 的类型枚举 + 白名单）

> 状态: DONE · 日期: 2026-09-22 · 效果: 实体数 2.42 → **7.17** 条/记忆，零实体条 12 条里从 1–2 条降到 **0**

## 问题与实测现状

近 6 周每周都有 **~25%** 的记忆**一个实体都没有**（29.5/24.7/18.1/27.1/21.0/28.4/27.7%），
近 14 天平均只有 **0.91 条实体链接/记忆**；而谱图通道承担 26% 的注入项（见
[召回通道消融](2026-09-22-recall-channel-ablation.md)）⇒ 图谱召回的天花板被压住。
**换模型前后一致（0.93 → 0.91）**，所以这不是模型切换造成的。

## 根因（两个叠加，都不是"模型不行"）

1. **prompt 自相矛盾**：`_get_prompt_with_relations` 的 **JSON schema 示例**只给了 4 类
   （`person/location/organization/event`），而下面的【实体类型】段列了 6 类（多了 preference/thing）。
   模型锚定 schema 示例 ⇒ 技术记忆（Redis 淘汰策略、WSL 路径、qmt-proxy 配置）里"不是人名地名"的
   关键实体被整批丢弃；【不要提取】段还把"系统/服务/配置/文件"列为泛指名词，进一步压制。
2. **白名单静默压平**（改动前发现的隐藏依赖）：后处理 `_filter_entities_with_types` 里
   `if entity_type not in ENTITY_TYPES: entity_type = "thing"` —— `ENTITY_TYPES`（`services/graph_tools.py`）
   只有 6 类。**若只改 prompt 不改白名单，新类型会被静默改成 `thing`**，类型收益归零。

## 实验（12 条真实记忆，含 4 条当前零实体；同批三变体 + 盲评）

| 变体 | 实体数（总/均/零实体条） | 关系数 | 会被存储过滤丢掉 |
|---|---|---|---|
| A1 现役 prompt | 29 / 2.42 / 1 | 17 | 1 |
| A2 现役 prompt 再跑 | 28 / 2.33 / 2 | 19 | 2 |
| **B 扩展版** | **86 / 7.17 / 0** | **79** | 15（17%） |

- 覆盖结构：B 覆盖现役输出的 **86%**（A1 vs B 召回 0.861），说明是**超集式增补**而非替换；
- 盲评（Qwen3.7-Max，含 low-vs-low 同配置对照）按维度拆：

| 维度 | 对照（A1 vs A2） | 主对比（A1 vs **B**） |
|---|---|---|
| accuracy | 4.50 vs 4.50 | **4.58 vs 4.58**（持平 ⇒ 多抽的不是幻觉） |
| completeness | 2.33 vs 2.08 | **1.67 → 4.67** |
| typing | 2.42 vs 2.42 | **1.58 → 3.83** |

## 改动

1. **`src/services/core/llm_entity_extraction.py`**：关系版 prompt（中文 + 英文同款）
   - JSON schema 示例改为具体示例（`dsh|software`、`张三|person`、`volatile-lru|config`）；
   - 【实体类型】扩到 15 类：原 6 类 + `software/system/service/config/version/protocol/technology/metric/concept`，
     每类给具体例子；
   - 加显式指令：**技术术语/命令/配置项/版本号/字段名/函数名/服务名都算实体**；
   - 【不要提取】第 1 条补例外：**带具体名字的技术名词必须提**，排除的只是"没有名字的泛指词"。
2. **`src/services/graph_tools.py`**：`ENTITY_TYPES` 白名单补上同名 9 类（**必须与 prompt 同步**）。
   影响面已核查：该白名单全仓**只有一处消费**（类型归一化），召回链路不按类型分支 ⇒ 扩展安全。
3. **测试**（`tests/test_v2/test_llm_entity_extraction.py` +2）：
   - 技术类类型**不被压成 thing**（锁住白名单）；
   - **prompt 类型清单 ⊆ 白名单**（防以后又单向改一处）。

## 线上验证

重启后真实写入一条技术记忆（Redis volatile-lru / qmt-proxy / gunicorn / pgvector / WSL2）：

```
TTL | concept      volatile-lru | config     gunicorn | service    qmt-proxy | service
Redis | software   WSL2 | system              pgvector | technology        ← 共 7 条，类型全精确
```

对照改动前的同类写入（1–2 条、且多为 `thing`）。`_status=completed` + `_processed_at` 同时确认正常（A 的终态机制）。

## 上线后复核发现的第二个问题：降级完全静默（同日已修）

复核线上"部署后仍有零实体"的那几条时，抓到一条 889 字符的技术记忆（本会话自己存的）：
- 写入时间 07:38:30 → 07:38:31 真的发出了提取请求 → 07:39:04 返回 `content_len=2207`（抽到了东西）
- 但该记忆最终 **0 实体，且 metadata 里连 `entities` 键都没有** ⇒ 抽取结果根本没被采纳
- 事后**无法归因**：`extract_with_relations` 的三条降级分支（超时 / 异常 / JSON 解析失败 **result 为空**）
  **全都没有任何日志**，只默默退回规则提取（对中文技术文本基本抽不出东西）

用生产实例（timeout=60）复跑同一条内容：**14 个实体 / 9 条关系** ⇒ 说明写入时那次是**偶发降级**
（最可能是那一次返回的 JSON 没解析成功），而这正是"~25% 零实体率查不清"的原因。

**修复**：给三条降级分支补 WARNING 日志（含类型、原因、文本长度），并给该模块补上模块级 `logger`
（此前整个模块**没有任何日志出口**）；新增回归测试断言"解析失败会留痕"。

**这条对后续观察很关键**：现在再出现零实体，日志能直接告诉我们是**超时**、**异常**还是**解析失败**，
而不是像这次一样只能靠事后复跑去猜。

## 已知边界与后续

- **裸版本号仍会被丢**：存储侧 `should_skip_entity` 的 `^v?\d+\.\d+` 规则会丢弃 `0.1.5-rc.2` 这类
  纯版本串（与 `0.85`/`100%` 同类）；带名字的形态（`Debian 12`、`pgvector 0.8.2`）能进图谱。
  已在测试里显式标注。要不要放宽属于**另一个待测改动**（放宽会同时放进纯数字噪音）。
- **存储过滤仍会吃掉约 17%** 的扩展版输出（`run_daily.py`、`fetch_market_indices()` 等技术标识符
  因"文件路径/纯 ASCII+斜杠点"规则被丢）。是否放宽同样待测。
- **观察指标**（跑几天后核对）：近 7 天"零实体记忆占比"应从 ~25% 显著下降——
  ```sql
  SELECT count(*) FILTER (WHERE NOT EXISTS (SELECT 1 FROM memory_entities x WHERE x.memory_id=m.id))::float
         / count(*) FROM memories m WHERE m.is_latest AND NOT m.is_forgotten
         AND m.created_at > now() - interval '7 days';
  ```
  若没降，说明瓶颈不在 prompt 而在别处（如写入路径未走到关系版提取），需再查。
- **未动**：非关系版 `_get_prompt`（`extract_relations=False` 才走，非生产路径，未测故未改）。
