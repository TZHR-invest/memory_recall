# 2026-08-13: ADR-0010 实施顺序讨论——插件先行 vs 强制统一更新

> 类型: 讨论 · 日期: 2026-08-13
> 关联: [ADR-0010](../decisions/0010-remove-document-rag.md)、[实施优先级讨论](2026-08-13-adr0010-implementation-discussion.md)
> 状态: 结论已给出，两个决策点待用户确认

## 背景

当前有 1-2 个真实用户在用的部署。用户提出实施顺序疑问：
先移除插件对文档的需求、后端兼容"存在文档/无文档"两种情况，等插件更新完再做后端删除；
还是强制所有插件与后端统一更新（一次切换）？

## 讨论要点

### 代码事实：旧插件 + 新后端（文档 API 已删）的故障形态

| 调用点 | 触发方式 | 后端删除后的行为 |
|--------|---------|-----------------|
| opencode FileWatcher（enableDocumentTracking 默认 true） | 文件变化自动 | importFile 抛错被 catch，仅一条 error 日志，不崩溃；已跟踪文件（.memory-recall-docs.json）不重试，噪音有限 |
| hermes / codex status 命令（GET /documents 计数） | 用户查状态 | 已有 try/except 容错，显示"文档 ?"，不影响输出 |
| 各插件文档 tools（list/read/delete/import-docs） | 用户手动 | 返回错误文本，仅该 tool 失败 |
| 记忆主链路（add/search/context-inject/profile） | — | 完全不碰文档 API，零影响 |

**结论：旧插件 + 新后端的故障形态是可控噪音，不是故障。**

### 方案分析

- **插件先行（用户方案 A 的一半）：有必要**。新插件不调用文档 API → 天然兼容旧后端，
  消除"旧插件 + 新后端"的噪音窗口，把用户升级动作与后端破坏性变更解耦；
- **后端兼容"存在文档/无文档"（用户方案 A 的另一半）：不必要且有害**：
  1. 兼容 = 存在性判断 + 双路径分支，正是 ADR-0010 要消灭的"第四条通道维护税"变体；
  2. 兼容窗口无自然退出条件，易变永久债务（solo 项目尤忌）；
  3. 上表已证明噪音可接受，无需兼容代码。
- **强制统一更新（用户方案 B）：不需要强制**。仓库内四端一起改（一个批次 commit）；
  用户侧是"发版 + 告知"的推式协调，个位数用户无需强制机制。

### 推荐方案：三阶段、单向兼容（新插件兼容旧后端，后端不做兼容）

1. **阶段 1 插件先行**：四端同时移除文档功能——opencode 发 npm 新版
   （删 document tools + FileWatcher 文档逻辑 + enableDocumentTracking 配置项），
   codex / hermes / deepseek-tui 同步删 document tools；
2. **阶段 2 用户升级**：1-2 个用户直接沟通：opencode 重装 npm 包
   （bunx memory-recall-opencode install）、codex 拉仓库代码、hermes/deepseek-tui 同步 server.py；
3. **阶段 3 后端一次删除**：确认用户升级后实施 ADR-0010 删除清单；
   **部署库 DROP TABLE 作为最后一步单独执行**（代码删除与数据删除分离，可延后到
   用户确认无回滚需求；无迁移框架下本就是手动操作，天然可分步）。

## 结论

推荐三阶段方案（插件先行发版 → 用户升级 → 后端一次删除 → DROP 延后），
后端**不写**兼容代码。

## 下一步

两个决策点待用户确认（2026-08-13 询问超时未答）：

1. 是否按三阶段方案调整实施计划（vs 保持 3-commit 一次切换 vs 后端兼容过渡）；
2. opencode npm 发布流程是否可用（可发布 / 改仓库安装 / 待定）。

确认后更新 [2026-08-13-adr0010-implementation-discussion.md](2026-08-13-adr0010-implementation-discussion.md)
的下一步并登记 STATUS.md。

## 未决问题

- 三阶段方案是否采纳（决策点 1）；
- opencode 发版方式（决策点 2）。
