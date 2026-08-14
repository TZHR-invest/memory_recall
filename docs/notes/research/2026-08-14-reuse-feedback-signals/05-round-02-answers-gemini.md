# round-02 · Gemini 回答原文

> 执行日期: 2026-08-14 · 会话: round-01 同一会话内继续追问 · 平台画像: 工程化、给出具体取舍（已剥离"Gemini 说"前缀）
> 提示词: [04-round-02-prompts.md](04-round-02-prompts.md) Gemini 追问块（原文回填，未二次概括）

---

这是这两个工程细节在实际落地时的核心解法与取舍逻辑：

一、 冲突判定与误判控制策略
1. 误判成本分析：宁可“误留”，绝不“误删”

在记忆系统里，两类错误成本极大不对等：

假阳性（False Positive，误判为冲突并删除旧记忆）：成本极高。AI 发生“记忆断层”，丢失历史演进背景，甚至需要用户重新解释一遍过去踩过的坑。

假阴性（False Negative，漏判冲突，新旧记忆并存）：成本中等且可控。如果召回时每条记忆都携带发生时间（Timestamp），LLM 在上下文推理（In-Context Reasoning）中能够天然根据时间先后自行消除大部分轻度矛盾。

核心原则：永不物理硬删除（No Hard Delete）。冲突处理的目标不是“淘汰旧数据”，而是“建立版本演进链（Lineage Graph）”。

2. 冲突判定的 4 步工程流水线

单靠向量相似度（Cosine Distance）无法判定“冲突”，因为“改为使用 PostgreSQL”和“继续使用 MySQL”在向量空间里语义极其接近（都是关于 DB 选择），必须依赖自然语言推理（NLI, Natural Language Inference）范式：

[用户纠错/新输入] 
       │
       ▼
1. 结构化抽取 ──► 提取主体-属性-断言 (Entity - Attribute - Claim)
       │
       ▼
2. 候选范围检索 ──► 按 Entity/Topic 强过滤，召回相关旧记忆 (Top 3-5)
       │
       ▼
3. NLI 分类判别 ──► LLM 判定：[Contradiction | Entailment | Partial_Update | Neutral]
       │
       ▼
4. 版本链更新 ──► 局部打补丁 或 标记 superseded_by=ID (软失效)

具体环节说明：

步骤 1：提取断言（Claims Extraction）
将用户纠错解构为结构化元组：

输入："我们项目不跑在 Docker 里了，改部署到 K8s 节点上，但本地调试依然保留 Docker Compose。"

抽取：

Claim A: Environment.Production = Kubernetes

Claim B: Environment.Local = Docker Compose

步骤 2 & 3：NLI 判定与冲突类型划分
将抽取出的新 Claim 与检索出的旧记忆对比，交由轻量 LLM（或专门 fine-tune 的 Classifier）判别，并区分三种状态：

判别结果	含义	处理策略
Full Contradiction	核心断言完全冲突（如："用 React" vs "用 Vue"）	旧记忆标记为 Superseded，指向新记忆 ID。不物理删除。
Partial Update	局部修正（如："版本从 React 17 升级到 18"）	保留旧记忆的核心背景，衍生出包含版本增量的新记忆节点，两者连接 Evolved_To 关系。
Entailment / Neutral	补充说明或无关	正常追加新记忆，不触发旧记忆状态变更。

阈值与安全机制：

NLI 置信度卡点：只有当 LLM 判定为 Contradiction 且置信度大于 0.85 时，才进行软失效（Superseded）标记。

延迟提交（Lazy Invalidation）：可以在后台静默标记“待失效（Pending_Superseded）”，直到该冲突在后续 2 次以上的交互中被再次印证，才正式更新状态。

二、 归档/提炼的粒度取舍

记忆提炼（Memory Consolidation）如果在单条粒度做，无法产生高维度的工程准则；如果在全局/项目粒度做，又会丢失局部上下文，并且极其消耗 Token。

结论：采用“两层记忆架构（Two-Tier Memory Architecture）”，在“主题/模块级（Meso-level）”进行归档提炼。

三种粒度的详细对比与取舍
粒度层级	代表形态	优点	缺点	适用场景


微观粒度




(Atomic Fact)

	单条事实（如 "用户配置了 Redis 端口为 6379"）	召回极其精准，注入 Token 开销小， conflict 检测容易。	极其碎片化，无法呈现系统的全貌或长期的“设计偏好”。	实时对话中的零碎变更、API 细节记录。


中观粒度 (推荐)




(Topic / Module)

	主题文档 / 规则集（如 "数据库迁移历史与当前 ORM 踩坑规范"）	最佳平衡点。符合开发者对系统的心理模型，提炼出的工程准则非常实用。	需要动态主题聚类，分类边缘可能存在模糊。	长期记忆提炼的主阵地（架构准则、排错指南、环境搭建规则）。


宏观粒度




(Project-wide)

	全局项目 Memory.md / README	视角全面，适合作为 System Prompt 的初始输入。	极易过期、Token 开销大，更新成本高，微小修改会导致整份文档失效。	仅适合生成高阶的项目 Vision 与整体技术栈清单。
推荐实践：流水线式的“原子-主题”提炼机制

建议将记忆库设计为类似于 Git Commit 机制与 Document 机制 的双层结构：

[对话/操作日志] ──► (追加) ──► [原子记忆列表 (Atomic Logs)]
                                     │
                                (定时/异步 Cron)
                                     ▼
                            [主题归档引擎 (Topic Synthesizer)]
                                     │
                                     ▼
                      ┌──────────────────────────────┐
                      │  Topic 1: 权限模块设计规范    │
                      │  Topic 2: 部署与 CI/CD 踩坑   │
                      │  Topic 3: 性能优化惯例        │
                      └──────────────────────────────┘


实时写入层（Atomic Layer）：
对话过程中捕获的所有“点状知识”全部作为原子日志（Log）写入数据库。

异步归档层（Topic Consolidation Engine）：
后台任务按 Topic（例如：Auth, Database, DevOps）将相关联的原子 Log 进行聚合：

输入该 Topic 下最新的 20 条原子日志与旧的主题文档。

让 LLM 执行 Compress & Synthesize 操作，合并重复项、删除过时内容（根据软失效标记）、提炼出结构化的“工程准则”（Engineering Rules）。

召回阶段：

优先检索并注入 主题归档文档（Topic Document） 提供整体上下文。

当检索得分极高时，再带上最新的 原子增量（Atomic Logs） 补充极细微的细节。

3. 知识出处说明

来自学术/开源工程实践：

NLI 与 Claim Extraction：借鉴了 RAG 评估与知识图谱对齐（Fact Verification）领域的标准范式，如 FEVER 框架及 Mem0 中基于 Entity-Attribute-Value 结构抽取冲突的思路。

Two-Tier Architecture：参考了 HippoRAG（Neurobiologically Inspired Long-Term Memory）以及类 Obsidian 的双层（Atomic Notes vs. MOC / Map of Content）知识组织形态。

来自推理与工程综合：

宁可“误留”不“误删”、引入软失效（Superseded）、以及利用时间戳交由 LLM 处理轻度矛盾，是 AI Agent 工程落地中控制数据丢失风险的经验总结（推演与实操归纳）。

针对这两点的进一步实现，可以从以下方向深入：
查看用于 NLI 冲突检测与 Claim 抽取的 Prompt 模板
探讨主题级（Topic）记忆聚类与动态路由的具体实现
