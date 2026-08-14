# Round 1 统一理解

> 类型: 调研（统一理解）
> 调研: 2026-08-14-memory-value-criteria
> 说明: 五平台（ChatGPT/Claude/Grok/Gemini/doubao）回答收敛；外部回答是素材不是事实，
> C 类结论回项目内验证后才可进 ADR / 根目录文档。

## 统一理解（Agent 填写）

### Q1 判据本体（ChatGPT / Claude / Grok）

| 判据 | 证据平台 | 证据强度 | 能否操作化 | 备注 |
|------|---------|---------|-----------|------|
| 检索多因子：relevance + recency + importance（Park et al. 2023 Generative Agents） | ChatGPT / Claude / Grok 全一致 | 原文事实 | 强（LLM 打 1-10 + embedding 相似度 + 时间衰减） | 公认基线；但只控检索排序，不控写入深度，本身无晋升机制 |
| 未来效用 / 可预测性（NEMORI，预测误差驱动） | Claude / Grok | 原文事实 | 强（prediction error 信号） | 少数学习出来而非人工设定的判据；直接对应未来还会被需要锚点 |
| 复用 / 检索频率（retrieval practice；knowledge reuse） | ChatGPT / Claude / Grok | ChatGPT 原文事实（Roediger & Karpicke 2006/07）；Grok/Claude 作信号 | 强（reuse_count，跨项目计数更佳） | 比 LLM 猜 importance 可靠；阈值是产品 heuristic 非文献值 |
| 再获取成本（Information Foraging；KM ROI） | ChatGPT / Grok / doubao | ChatGPT 原文事实（Pirolli & Card 1999）；doubao 社区实践 | 强（reacquisition_cost 拆 user_input+search+read+reason+verify） | 见 Q3 |
| 原子性 + 可链接性（Zettelkasten） | ChatGPT / Grok | 原文事实 | 强（单知识单元 + 可被独立 query 召回） | 一条 memory = 一个独立 claim/fact/rule/decision |
| 证据 / 可靠性 / 可重复性（DIKW 后扩展；Yao et al.） | ChatGPT / Claude | 原文事实 | 中-强（evidence_count、source_count、contradiction_count） | 单次观察不得自动升级为稳定知识 |
| 反思 / 从经验到高层（Generative Agents reflection；Nonaka SECI 显性化） | ChatGPT / Claude / Grok | 原文事实 | 强（是否已产生更高层解释；tacit→explicit） | reflection 本身是记忆，参与检索 |
| 意外性 / 冲突（NEMORI prediction error 推论） | Claude / Grok / doubao | Claude 原文事实；Grok 原文事实 | 强（与新记忆冲突检测） | 超出预期的信息 = 环境/偏好变化信号 |
| 重复出现次数 / 一致性阈值 | Claude（推断）/ Gemini（推断） | 推断 | 中（连续 N 次同类事件触发抽象） | 原文只描述现象，无具体 N 值 |
| 显式用户信号（Forte keep what resonates；用户说记住这个） | ChatGPT / Grok | 原文事实（Forte 2022） | 强（explicit user signal 权重高于 LLM 自评） | capture 标准是选择性捕获，非全量 |

**统一结论（Q1）**：五平台收敛于多判据组合、行为信号优于 LLM 自评。无单一文献给出统一公式或
普适阈值（五平台一致标注【不知道】）；ChatGPT/Claude 明确建议：先低成本捕获 → 行为证据 →
consolidation → promotion 的三级生命周期，而非首次出现即判晋升。promotion 判据候选集：
future relevance、miss/reacquisition cost、reuse frequency、transferability、reliability、
atomicity、explicitness（用户显式）——与调研前假设 1/2/3/4/5 高度吻合，新增显式用户信号（假设缺失项）。

### Q2 项目内 vs 跨项目（ChatGPT / doubao）

| 观点 | ChatGPT | doubao | 证据强度 |
|------|---------|--------|---------|
| 核心判据 = 是否依赖本项目/当前环境（dependency footprint） | 是（dependency footprint 概念） | 是（依赖绑定；检验拿到新项目是否仍保真） | 两平台一致 |
| 项目内/跨项目 = 连续谱而非二分类 | 是（user principle → domain → tech → project pattern → environment → ephemeral） | 是（底层判据相同、信号清单不同） | 一致，但均属推断/工程化整理 |
| 跨项目知识须剥离项目唯一实体（仓库路径、文件名、实例 ID 等） | 是（entity dependency 信号） | 是（禁止跨项目复用信号清单） | 一致 |
| 跨项目复用信号 = 通用踩坑根因、工具原生行为、用户长期稳定偏好、领域标准 | 部分（transferability/abstraction level） | 明确列举 | doubao 更具体（中文社区实践）；ChatGPT 更抽象（学术框架） |
| 可操作化测试 = 复制到全新同领域项目不加修改是否仍为真 | 隐含（transferability = P(另一 project 有用)） | 明确给出 prompt | 一致方向 |
| 两条不同 promotion pipeline（project vs general） | 明确 | 隐含（双层记忆路由） | 一致方向 |

**统一结论（Q2）**：项目内 vs 跨项目**不是价值差异，而是 scope/晋升去向差异**（ChatGPT 明确：
跨项目性不是 memory value 的必要条件，只是决定 scope/promotion destination）。区分信号 =
dependency footprint（project / environment / temporal / entity / abstraction level），
可操作化为剥离本项目实体后是否仍成立。doubao 补充中文社区实践：scope:global 显式标记、
reusable_patterns 进全局、项目专属配置放项目域。→ 映射本项目 6 维命题模型的归属/载体维度
（container_tag 已隐式编码 {keyId}_project-<dir>）。

### Q3 价值度量（ChatGPT / Grok / doubao）

| 度量 | 来源 | 证据强度 | 落地 |
|------|------|---------|------|
| Expected Avoided Reacquisition Cost（预期避免的再获取成本） | ChatGPT 工程模型（基于 Pirolli & Card 1999 Information Foraging） | ChatGPT：原文事实（理论基础）+ 推断（公式）；Grok/doubao 同向 | 核心指标；行为数据可校准 |
| 价值 Score ≈ P(未来被需要) × C(再获取成本) | Grok / doubao 明确公式；ChatGPT 更细（×T×R×S − 维护/错误/检索成本） | 全部推断（无文献原话） | P 代理：复用频次、同主题查询密度、知识类型；C 代理：token/时间/工具轮次 |
| 复用频率（retrieval/reuse count + 衰减） | ChatGPT（retrieval practice 文献）/ Grok / doubao | 原文事实 + 工程化 | reuse_count、reuse_count_7d/30d、cross_project_reuse_count、success_rate |
| 未来被引用概率（prediction/query demand） | ChatGPT（future citation probability）/ Grok（NEMORI）/ doubao（MemoryCPT QPC） | 原文事实（NEMORI/2608.04843）+ 代理 | LLM 估计 + 历史 retrieval success rate 后验；MemSIF Delayed Utility Manifestation |
| 蒸馏后检索质量保持 | Grok | 原文事实（arXiv:2603.13017） | 蒸馏替代原文的准入条件 |

**统一结论（Q3）**：三平台一致收敛于 **value ≈ P(future need) × C(reacquisition)**，两个因子
均有可操作代理；核心指标倾向 Expected Avoided Reacquisition Cost（最贴锚点、可用真实行为数据
校准）。无文献给出精确耗时/概率分布（三平台一致【不知道】）；阈值由产品数据学习。→ 映射本项目：
confidence 之外的新信号（reuse_count / reacquisition_cost / cross_project_reuse_count），
可作晋升模型输入。

### Q4 晋升 / 抽象时点（Claude / Gemini）

| 观点 | 证据强度 | 说明 |
|------|---------|------|
| Tulving 1972：episodic（情境、自我关联、时间空间细节）vs semantic（去情境化、通用） | 原文事实（两平台） | 相互依赖、非互斥二分 |
| CLS 互补学习系统（McClelland 1995）：经验经海马体快速编码 → 重放 → 逐渐训练皮层语义表征 | 原文事实（Claude 二手转引；Gemini 同类图式理论 Winocur & Moscovitch 2011） | 转化是渐进过程，非一次性判断 |
| Generative Agents reflection：importance 累计超阈值（150）触发抽象；收集最近 100 条 → 提 3 个高阶问题 → 蒸馏洞察写回 + 指针树 | 原文事实（两平台一致） | 数值阈值来自实现，非通用定律 |
| NEMORI 两阶段：episodic integration（原始交互→连贯叙事）→ semantic distillation（预测误差驱动） | 原文事实（两平台） | 目前少数把何时抽象建模成信号（可预测性/惊讶度）而非隔多久摘要一次的方案 |
| 何时保留原始记录：时间/空间/因果细节本身未来要用时（如某次部署导致故障）不抽象 | Claude 推断；Gemini 推断（结合工程规范） | 过早抽象丢失可验证性/可追溯性 |
| 落地建议：双写——原始 episode 永久保留（不删除、只降权），语义抽象异步生成且带回链；抽象触发优先意外性/冲突而非定时摘要 | Claude 推断 / Gemini 推断 | 两平台独立收敛，工程建议 |

**统一结论（Q4）**：两平台一致：episodic→semantic 是**渐进转化（重放/重复接触）**，触发信号用
**意外性/冲突（prediction error）** 而非定时摘要；抽象后原始记录保留（降权 + 指针回链）。
数值阈值（150/N 次）属实现启发式，无普适定律（两平台【不知道】）。→ 映射本项目：
create_derived_memory（is_inference=TRUE + derives 边）正是派生记忆载体——应保证 derived
记忆带 source 指针（memory_relations 已有 derives 边），原始记录不删只降权。

### Q5 负例 / 污染（Claude / Gemini）

| 失效模式 | 证据 | 防护 |
|---------|------|------|
| 幻觉（一开始就错，Memorization Hallucination） | Claude 原文事实（LLM-based Agents Survey；SSGM） | 准入前正确性验证（Adaptive Memory Admission Control） |
| 过时（当时对现在错，temporal obsolescence） | Claude 原文事实（Zep/Rasmussen 2025；STALE 三类失效） | 时效戳 + 冲突消解（SUPERSEDE 判定 + 更新链） |
| 漂移（反复摘要逐渐失真，semantic drift） | Claude 原文事实（arXiv 2605.12978：持续更新使有用记忆变 faulty） | 限制迭代摘要代数、溯源链接、定期用原始记录校验重建 |
| 投毒（外部恶意注入，AgentPoison 0.1% 注入 80% 成功率） | Claude 原文事实（AgentPoison Chen et al. 2024；DSRM） | 检测层效果有限 → 准入与权限控制优先；结构解耦（生成策略与存储介质分离） |
| 错误泛化（False Generalization：局部解法误提取为全局规则） | Gemini 原文事实 | 反例验证 + 作用域限定：连续 N 个不同上下文验证或用户确认才晋升；显式标注 Scope |
| 前提诱导偏见（Premise-Induced Bias）/ 状态冲突（Implicit Conflict） | Gemini 原文事实（STALE 2026） | 注入前提修正 System Note：[User premise assumes X, but X updated to Y] |
| 干扰 / 错误记忆（认知：DRM、Loftus & Palmer 1974） | Claude / Gemini 原文事实 | 类比：污染发生在编码后、巩固前窗口 → 新信息须与旧记忆做冲突检测 |
| 原始证据 vs 推理衍生隔离 | Claude（SSGM 结构解耦）/ Gemini（Source Pointer） | Ground Truth Log 与 Derived Knowledge 分离；Derived 带 Source Pointer，可一键重蒸馏/Purge |

**统一结论（Q5）**：两平台一致：**四类失效模式（幻觉/过时/漂移/投毒）防护机制不同，不能用同一套
置信度分数应付**（Claude 明确）。共同防护原则：(a) 准入前验证；(b) 冲突/取代判定（对应本项目
is_latest 语义——但注意调研区分取代与修订两种语义，与本项目设计一致）；(c) 原始与衍生隔离
+ Source Pointer；(d) 反例验证 + 作用域限定（防错误泛化，对应 6 维适用条件维度）；(e) 限制迭代
摘要代数。→ 本项目已有 is_latest/is_inference/memory_relations.derives 与调研结论吻合，
无需新增机制；适用条件必须显式（假设 6）获 Gemini False Generalization 支持。

## 调研前假设的验证结果

| # | 假设 | 验证 |
|---|------|------|
| 1 | 跨上下文复现 | ✅ Claude 推断（重复出现/一致性阈值）+ Gemini（连续 N 次）——成立，但无文献数值 |
| 2 | 被纠正/冲突 | ✅ Claude（NEMORI prediction error/冲突）+ Gemini（Implicit Conflict、SUPERSEDE）——强支持 |
| 3 | 复用频率 | ✅ 五平台中最一致的信号（retrieval practice / knowledge reuse / Memory Reuse Rate） |
| 4 | 再获取成本 | ✅ 最贴锚点；ChatGPT 核心指标 Expected Avoided Reacquisition Cost；Pirolli & Card 1999 提供理论基础 |
| 5 | 时效稳定性 | ✅ Claude（temporal obsolescence）+ Gemini（STALE）——但更多是失效防护而非晋升判据，两者都要 |
| 6 | 适用条件显式 | ✅ Gemini False Generalization（作用域限定）——晋升 gating 的必要条件 |
| （新增） | 显式用户信号 | ➕ Forte（ChatGPT/Grok）——用户说记住这个应高权重直入 |

## 停止条件评估

关键事实（Park 2023 基线、NEMORI 预测误差、reuse frequency、reacquisition cost、
Tulving/CLS 理论、四类失效模式）已达 ≥2 平台一致 + 可溯源文献收敛标准；数值阈值类（150/N 次）
为实现启发式，属【不知道】类，不追。本轮无需追问轮；进入收敛轮（回项目内映射验证）。
