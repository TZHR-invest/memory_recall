# 2026-08-14: 命题成熟度引擎——晋升方法论讨论总纲

> 类型: 讨论（方向重定位 + 讨论路线图）· 日期: 2026-08-14
> 关联: [memory-confidence](2026-08-14-memory-confidence.md)（S2）· [memory-layering-and-recall](2026-08-14-memory-layering-and-recall.md)（S3/S5）·
> [personal-vs-shared-boundary](2026-08-14-personal-vs-shared-boundary.md)（S4）· [workbench-vs-debug-roles](2026-08-14-workbench-vs-debug-roles.md)（S3）· [promotion-judgment](2026-08-14-promotion-judgment.md)（S0+S1 判据）·
> MR-006（统一知识对象）· MR-008 · MR-011 · MR-019

## 背景

同日的 4 篇 note（confidence / layering-and-recall / personal-vs-shared-boundary / workbench-vs-debug-roles）
是在「记忆 vs 知识库」的旧框架下拆出的 4 个平行 topic。讨论推进后，产品定位发生重定位：

**终态不是"个人记忆缓存"，而是覆盖「记忆 → 个人知识 → 团队知识」全流程的"命题成熟度引擎"；
灵魂是"提炼（情景→语义）"这一次质变。**

本文记录这个重定位，把 4 篇旧 note 重新挂到主线上，并标出缺失的"提炼"心脏。

## 核心共识（方向已重定位，未拍板）

1. **命题（proposition）是统一原子单元**：记忆与知识都是命题，只是成熟度不同 → 即 MR-006 的"统一知识对象"。
2. **命题有 6 个维度**，分两类：
   - 内在（语义）：内容 / 适用条件 / 置信度 / 时效 / 泛化性；
   - 系统（工程）：归属 / 载体。
   - （2026-08-14 决策，Q2 回主线）「置信度」拆成正交**两轴**：**内容置信度**（correctness/staleness/harmfulness）
     ∥ **复用置信度**（P(useful|M,C)）——对应 v2 判据里"内容对不对 vs 用了有没有用"两个不同因子，
     由证据累积推导，不再写入时一次性设定。详见 [memory-confidence](2026-08-14-memory-confidence.md)。
3. **成熟 = 两次量变 + 一次质变 + 一次迁移**：
   - 记忆 ↔ 长期记忆 = 量变（置信度↑、时效↑，连续谱无分界）；
   - 长期记忆 → 个人知识 = 质变（**情景 → 语义**，这是灵魂）；
   - 个人知识 → 团队知识 = 归属迁移（命题内容不变，归属/载体变）。
4. **记忆与长期记忆无明确界限**，只有置信度/时效的连续差异；"提炼为个人知识"才是关键晋升。

## 4 篇旧 note 重新挂点

| 旧 note | 新位置 | 角色 |
|---------|--------|------|
| [memory-confidence](2026-08-14-memory-confidence.md) | S2 信号 | 晋升的置信度涨落（门槛输入） |
| [memory-layering-and-recall](2026-08-14-memory-layering-and-recall.md) | S3 触发 + S5 消费 | 生命周期 + 召回使用 |
| [personal-vs-shared-boundary](2026-08-14-personal-vs-shared-boundary.md) | S4 迁移 | 团队知识的归属/载体 |
| [workbench-vs-debug-roles](2026-08-14-workbench-vs-debug-roles.md) | S3 裁决 | 人确认/纠错（晋升的判定界面） |

**缺口（进行中）**：[promotion-judgment](2026-08-14-promotion-judgment.md) 记录了 S0+S1 第一轮判据讨论（四桶 + P×C），但"提炼/泛化机制本身"仍未拍板。

## 结论

方向已重定位，主体未拍板；本 note 是 S0–S5 讨论路线图的总纲。**已拍板的增量（2026-08-14，Q2 调研回主线）**：

1. **遥测基座独立为 S-pre**：不并入 S2——它是 S1（晋升判据）、S2（涨落）、S3（workbench 裁决）三者的
   共同输入；先建 Memory→Decision→Action→Outcome 事件链 + 证据回写，后三者才不落空。
2. **「置信度」拆两轴**：内容置信度 ∥ 复用置信度（见上文 6 维度），由证据推导，写入时不再设死。
3. **先做插件信号面盘点**（Q2 C 类验证项 #1）：确定每端插件实际能采到的信号，再定 S-pre 埋点范围。

## 下一步（讨论路线图）

| 步 | 聊什么 | 产出 | 对应 |
|----|--------|------|------|
| **S-pre** | **遥测基座**：Memory→Decision→Action→Outcome 事件链 + 证据回写（使用/结果遥测） | 事件 schema + 埋点 | Q2 调研（reuse-feedback-signals），S1/S2/S3 的共同输入 |
| S0 | 命题 6 维度模型定死 | 共同词汇表 | = MR-006 重述 |
| S1 | 提炼机制：情景→语义的判据与抽象 | 质变定义 | 新开（心脏） |
| S2 | 置信度涨落 | 提炼的输入信号 | memory-confidence |
| S3 | 触发 + 判定（谁触发、谁拍板） | 晋升开关 | layering（触发）+ workbench（裁决） |
| S4 | 归属迁移（个人知识→团队知识、载体） | 迁移规则 | personal-vs-shared-boundary |
| S5 | 召回（注入/查询） | 消费端 | memory-layering-and-recall |

- **S-pre 与 S2 咬合紧**（遥测是 S2 的证据输入），先聊；S-pre 阶段 0/1 见 [Q2 调研](research/2026-08-14-reuse-feedback-signals/99-final-conclusions.md) 第四节；
- S0 与 S1 咬合紧，建议一起聊；
- S5 相对独立，可随时插入。

## 未决问题

- **情景 vs 语义的判据**（S0+S1 第一刀）：
  - 「上周四我把 user_tag 改错导致 2 个测试挂」= 情景？
  - 「Entity 模型字段是 container_tag 不是 user_tag」= 语义？
  - 「export HTTP_PROXY 加速 npm（适用条件：中国无翻墙设备）」= 语义？
  - 判据是"有无具体时空/代词"，还是"去掉上下文后命题是否仍为真且可复用"？
- 置信度涨落规则（S2）；触发/判定（S3）；归属迁移与载体 git vs db（S4）。
