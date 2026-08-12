# MR-018: profile 写入路径无 embedding，semantic_dedup 对画像失效

> 状态: OPEN · 严重度: P2 · 创建: 2026-08-13

## 问题

`context_inject_service._collect_items`（L748-755）给 profile static/dynamic 构建
`DedupItem` 时**只传 content/source，未传 embedding** → `semantic_dedup_service.deduplicate`
走 `items_without_embedding` 分支直接 `kept.extend()`，**画像项完全不参与去重**。

实际后果：用户画像内出现近似重复条目无法被自动去重。实证：主容器 18 条 static 中
2 条"重启服务"行为规则（mem_9a7be81f / mem_4b43a566，同 2026-05-19 创建，difflib ratio 0.709）
同时全量注入，浪费 token 且属数据冗余。

## 处理（2026-08-13，Oracle 裁定）

- **不做代码侧去重**：`_get_profile` 层 difflib 去重（阈值 0.7、保留第一条）误伤风险真实存在
  （短中文串 ratio 不稳定、可能丢弃语义不同的共享词汇规则、可能保留不完整版），
  且"行为规则永不截断"是测试锁定的设计意图——读取侧丢弃行为规则 = 新失败模式，远重于省 ~90 tokens。
- **数据侧清理**：forget 较短冗余记录 mem_9a7be81f（"用户说'需要重启服务'...直接执行重启操作"），
  保留完整版 mem_4b43a566（含"用户明确的偏好"句）。实际注入 static 18→17。
- **dynamic 44→5 保持现状**（时效即价值，配置旋钮非缺陷）；**static 不做 query 相关性过滤**
  （行为规则是无条件指令，过滤会让行为不确定）。

## 建议（仅当问题频发时）

若用户画像重复条目从一次性事故演变为**反复出现**，再回到代码层：
给 profile 写入路径的 `DedupItem` 补 embedding，让 `semantic_dedup` 在写入时拦截。
当前 18 条仅 1 组重复，远未到该阈值。

## 解决记录

（修复后填写 commit / 版本）
