# 02 · 给执行 agent 的完整上下文（自包含）

> 你（执行 agent）看不到本项目的对话历史。请先完整读本文件，再读 [01-goals.md](01-goals.md) 的
> "已知源码事实"与"现有假设"，然后执行外部调研，产出写入本目录 `99-final-conclusions.md`。

## 任务

做一次外部文献调研，回答一个核心问题：

> 在一个 agent 开发助手的记忆系统里，判断"一条信息值不值得记住、值不值得从临时记录晋升为可复用知识"的
> 判据是什么？这些判据能否变成可操作 / 可计算的信号？

## 价值锚点（判断"值得"的标尺，勿偏离）

- agent 做项目开发，很多用户已知的信息不应重复输入；
- 记忆对象：项目产生的信息、用户输入、项目现状 / 规划设计、开发环境，以及跨项目复用的项目无关知识；
- **价值 = 未来还会被需要，且忘记会导致重复成本（用户重新输入 / agent 重新查·推）**；
- 两层范围：项目内 + 跨项目（项目无关、可迁移）。

## 必须回答的 5 个问题（带搜索方向）

**Q1 判据本体**：agent 记忆 / 认知科学 / 知识管理里，"值得保留或晋升为知识"的判据有哪些？怎么操作化？
- 搜：cognitive memory consolidation；"generative agents" reflection（Park et al. 2023）；MemGPT / memory
  distillation in LLM agents；Tiago Forte "Building a Second Brain" capture criteria；Zettelkasten（Luhmann）
  atomic notes；progressive summarization；DIKW pyramid；Nonaka SECI tacit-to-explicit。
- 产出：候选判据列表，每条 = 名称 + 谁提出 + 怎么操作化（能否变信号 / 阈值）+ 证据。

**Q2 项目内 vs 跨项目**：怎么识别"项目无关、可跨项目复用"的知识？和项目内知识判据是否不同？
- 搜：agent memory global vs project-scoped；knowledge transferability / reuse；context-dependent knowledge；
  "applicability condition"。
- 产出：区分两类的识别信号（尤其：判据是否引用"本项目 / 当前环境"）。

**Q3 价值度量**："重复输入 / 再获取成本"作为记忆价值度量，有没有可操作近似？
- 搜：PKM capture criteria（Forte resonance）；cognitive retrieval cost；agent memory "future reference
  probability" / recall likelihood。
- 产出：把"值得记"变成可估计信号的方法（复用频率 / 再获取时间 / 被再次需要概率）。

**Q4 晋升 / 抽象时点**：文献怎么处理"具体经历 → 通用知识"的转化？何时抽象、何时保留原始记录？
- 搜：Tulving 1972 episodic vs semantic memory；schema / decontextualization；generative agents reflection /
  abstraction operators；memory distillation。
- 产出：抽象 / 晋升的触发判据 + "什么不该抽象"。

**Q5 负例 / 污染**：有没有"记了反而有害"（错误泛化、过时误导、记忆污染）？怎么防？
- 搜：LLM agent memory hallucination / stale knowledge；false generalization；PKM "what not to capture"；
  cognitive false memory / interference。
- 产出：晋升的安全阀（如"适用条件必须显式"）。

## 执行方式

1. 用 `web_search` 检索 + 直接读一手资料（论文 / 官方文档 / 知名博客），不要凭记忆脑补；
2. 每问 2-4 个来源起步；结论冲突时交叉验证（三阶段漏斗精神：定向 → 交叉 → 收敛）；
3. 来源优先级：一手 > 二手；论文 / 官方文档 > 营销软文。

## 提问纪律（每条结论都遵守）

- 区分【原文事实】【推断】【不知道】三档，不确定就写不知道；
- 每条判据 / 结论给来源 URL（或论文名 + 作者 + 年份）；
- 不要把你自己的观点写成"文献说"。

## 产出（写入 `99-final-conclusions.md`）

1. **候选判据对照表**（核心交付物）：

   | 判据 | 通俗含义 | 出处(链接) | 怎么操作化(信号/阈值) | 适用(项目内/跨项目) | 证据(原文/推断) |
   |------|----------|-----------|----------------------|--------------------|----------------|

2. **每问的发现**（Q1–Q5 各一段，标注原文 / 推断）；
3. **与现有假设对照**（01-goals.md 的 6 条假设：逐条标"证实 / 证伪 / 文献无涉 / 新增"）；
4. **未决 / 冲突**（哪些判据文献互相矛盾，证据倾向哪边）。

## 不做什么

- 不改代码、不写 ADR、不写 docs 根目录文档、不做落地设计；
- 只产调研对照表；结论是"C 类素材"，进 ADR 前需项目内验证。

## 输出文件

- 主产出：`99-final-conclusions.md`
- 可选中间记录：`NN-round-NN-*.md`（多轮时）
