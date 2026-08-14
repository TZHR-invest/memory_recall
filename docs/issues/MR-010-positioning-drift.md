# MR-010: 产品定位漂移：文档与代码讲了三套故事

> 状态: OPEN · 严重度: P0 · 创建: 2026-08-12
> 关联: [ADR-0001](../decisions/0001-product-positioning.md)

## 问题

根 README 说"AI 的长期记忆系统"；`docs/archive/requirements.md` 与旧 docs/README 是
"人类记忆 + Agent 记忆"双使命（照片 EXIF、位置、语音、need_confirm）；`apps/api/README.md`
仍停留在 v1 时代（`/api/v1/memories`、`{code,message,data}` 信封，与实际 v5 路由不符）。
人类记忆愿景均未实现，实际产品是 Agent 记忆。

2026-08-14 更新：讨论已将定位进一步上探为「命题成熟度引擎」（记忆 → 个人知识 → 团队知识，
灵魂是"提炼（情景→语义）"），见 [notes/2026-08-14-proposition-promotion.md](../notes/2026-08-14-proposition-promotion.md)。
由此，"Memory Recall" 这个名字已落后于愿景——它只命名了「记忆 + 召回」两个角落（低信任端 + S5 消费端），
漏掉灵魂（提炼）与终点（个人知识 / 团队知识）。**命名漂移是本 issue 的一个新症状。**

## 建议

以 [PROJECT_PLAN.md](../PROJECT_PLAN.md) 的定位为准（ADR-0001），统一各 README 叙述；
`apps/api/README.md` 按当前 API 重写。

命名：暂不改名（定位 O1 未拍板 + 改名成本高 + 改名过早会造成"名字比产品大"的反向漂移）；
待 O1 拍板成 ADR、或晋升管线真正开工时，随定位一起重定名。新名应承诺"提炼 / 成长"而非"召回"。

## 解决记录

（修复后填写 commit / 版本）
