# 2026-08-14: 命题成熟度引擎——晋升方法论讨论总纲

> 类型: 讨论（方向重定位 + 讨论路线图）· 日期: 2026-08-14
> 关联: [memory-confidence](2026-08-14-memory-confidence.md)（S2）· [memory-layering-and-recall](2026-08-14-memory-layering-and-recall.md)（S3/S5）·
> [personal-vs-shared-boundary](2026-08-14-personal-vs-shared-boundary.md)（S4）· [workbench-vs-debug-roles](2026-08-14-workbench-vs-debug-roles.md)（S3）·
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

**缺口**：没有 note 覆盖"提炼/泛化机制本身"（情景→语义）——即 S1，这是灵魂，需新开。

## 结论

暂无（方向已重定位，未拍板）。本 note 是 S0–S5 讨论路线图的总纲。

## 下一步（讨论路线图）

| 步 | 聊什么 | 产出 | 对应 |
|----|--------|------|------|
| S0 | 命题 6 维度模型定死 | 共同词汇表 | = MR-006 重述 |
| S1 | 提炼机制：情景→语义的判据与抽象 | 质变定义 | 新开（心脏） |
| S2 | 置信度涨落 | 提炼的输入信号 | memory-confidence |
| S3 | 触发 + 判定（谁触发、谁拍板） | 晋升开关 | layering（触发）+ workbench（裁决） |
| S4 | 归属迁移（个人知识→团队知识、载体） | 迁移规则 | personal-vs-shared-boundary |
| S5 | 召回（注入/查询） | 消费端 | memory-layering-and-recall |

- S0 与 S1 咬合紧，建议一起聊；
- S5 相对独立，可随时插入。

## 未决问题

- **情景 vs 语义的判据**（S0+S1 第一刀）：
  - 「上周四我把 user_tag 改错导致 2 个测试挂」= 情景？
  - 「Entity 模型字段是 container_tag 不是 user_tag」= 语义？
  - 「export HTTP_PROXY 加速 npm（适用条件：中国无翻墙设备）」= 语义？
  - 判据是"有无具体时空/代词"，还是"去掉上下文后命题是否仍为真且可复用"？
- 置信度涨落规则（S2）；触发/判定（S3）；归属迁移与载体 git vs db（S4）。
