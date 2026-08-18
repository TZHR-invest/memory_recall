# 专项文档（Initiatives）

> 状态: ACTIVE · 最后更新: 2026-08-18

存放**专项（initiative）**文档：一段有明确目标、跨多个里程碑、由多份文档组成的
长期工作（如"crystal：目标模型迭代替换 v5"）。一个专项一个子目录。

专项与单个 feature 设计的区别：

| | 单个 feature 设计（`docs/designs/`） | 专项（`docs/initiatives/`） |
|--|-------------------------------------|------------------------------|
| 规模 | 一份设计 + 版本线 | 一包文档（语义 / 落库 / 工程 / 需求 / 规划） |
| 版本化 | `v1.md` → `v2.md`，`LATEST.md` 指向当前生效 | **每份文档独立版本化**，包级一致性用「当前配套版本」表维护 |
| 生命周期 | 草稿 → 生效 → 被取代 | 立项 → 推进 → 交付 → **整目录归档** `docs/archive/initiatives/` |
| 入口 | `LATEST.md`（指针 + 摘要） | 目录内 `README.md`（文件地图 + 配套版本 + 进展） |

## 结构

```
docs/initiatives/<initiative-slug>/
├── README.md        # 专项入口：文件地图 + 当前配套版本 + 进展（必建）
├── prd.md           # 需求（可选）
├── milestone.md     # 规划 / 里程碑（可选）
└── ...              # 各层设计/契约文档，各自独立版本化
```

## 规则

1. **一个专项一个子目录**，slug 用短横线小写（如 `crystal`）；
2. **目录内 README.md 必建**，承担三件事：
   - 文件地图（每份文档的角色 / 层 / 版本化方式）；
   - **「当前配套版本」表**：按里程碑或阶段声明当前生效的文档组合
     （解决"这包文档当前以哪组版本为准"——专项没有单一版本线）；
   - 进展与待落文档清单；
3. **每份文档独立版本化**，各自带 `状态` + 版本 + 最后更新；
   **不设 LATEST 指针**（专项是文档集合，不是单个文档的版本线）；
4. **需求 / 规划类文档**（prd、milestone）放专项目录内，不进 `docs/designs/`——
   `designs/` 只放设计类文档；
5. 专项内文档遵循 [DOCUMENTATION_GUIDE](../DOCUMENTATION_GUIDE.md) 的头部与状态约定；
   新增文档时更新 README 文件地图与配套版本表；
6. **交付后整目录归档**：`git mv docs/initiatives/<slug> docs/archive/initiatives/<slug>`，
   并在 [archive README](../archive/README.md) 补一行原因；归档前在 README 标注最终状态。

## 现有专项

| 专项 | 入口 | 状态 |
|------|------|------|
| [crystal](crystal/README.md)（目标模型迭代替换 v5） | [crystal/](crystal/) | 推进中（M1 前置文档已齐） |

*状态: ACTIVE · 最后更新: 2026-08-18*
