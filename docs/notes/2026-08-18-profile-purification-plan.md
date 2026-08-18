# 用户画像净化 · 可执行方案（2026-08-18）

> 状态: 待批准执行 · 2026-08-18
> 背景：用户画像（用户容器 static）43 条 / 11KB，注入占 context 69-98%；混入非 preference 内容。
> 依据：既定 Oracle 裁定——"static 仅应存储 preference 类型的内容"、"行为规则永不截断是锁定设计"、
>       不做 difflib 去重、不做 query 相关性过滤、画像重复只能数据侧清理（MR-018）。

## 1. 核心思路

**画像回归"纯 preference"（遵循既定原则）+ 非 preference 降级 dynamic（不丢召回）+ 写入侧约束（防复发）。**

关键认知（经实测验证）：
- 降级 static→dynamic **不丢召回**：记忆注入（_get_memories）走向量检索，不区分 is_static
  （实测：防崩纪律降级后 query 相关时相似度 0.623 仍命中）
- 画像与记忆独立取数（_apply_injection_caps：profile 不裁剪、memory 各 cap 6）——画像不挤占记忆条数
- "static 仅存 preference"是既定原则，非 preference 混入会侵蚀画像/静态注入

## 2. 第一步：画像净化（数据操作，可回滚）

用户容器 43 条 static 分类：

| 分类 | 数量 | 处理 |
|------|------|------|
| preference（真偏好） | 12 条 | 保留 static（进画像） |
| learned-pattern/error-solution 等通用规则 | 23 条 | 降级 dynamic（UPDATE is_static=FALSE） |
| 项目性/一次性内容（auto_publish、key 吊销、主机名、metaso key、dsh-vision 配置等） | 8 条 | 降级 dynamic + 建议 forget（可恢复） |

SQL（先出清单确认，再执行）：
```sql
-- 降级清单（先确认）
SELECT id, metadata->>'type' AS type, left(content, 60) FROM memories
WHERE container_tag='085288ba-8eab-439b-b0d4-b92382e0f95d'
  AND is_latest=TRUE AND is_forgotten=FALSE AND is_static=TRUE
  AND COALESCE(metadata->>'type','') != 'preference';
-- 执行降级
UPDATE memories SET is_static=FALSE WHERE id IN (...);
```

效果：画像 43→12 条，体积 11KB→~3KB，注入占比 85%→~40%。
回滚：id 清单已存档，UPDATE 回 TRUE。

## 3. 第二步：写入侧约束（防复发，机制级）

**3.1 memory_store 工具层提示（不拦截，低风险）**
- tools.js：`scope=user && isStatic && type≠preference` 时响应追加提示：
  "⚠️ 用户级静态记忆应为 preference（用户偏好/永久特征）；跨项目规则建议 scope=project 或非 static（仍可被召回）"
- 原理：把"该不该进画像"的判断留给写入方（agent），工具只提醒。防崩纪律这类跨项目规则 agent 写时可自行决定；auto_publish 这类项目 bug agent 看到提示会意识到该存 project。

**3.2 后端 create 路径强制降级（可选，需谨慎）**
- create()：`is_static=true 且 type≠preference` 时自动降级 dynamic（遵循原则）
- ⚠️ 边界：只对"调用方显式传 isStatic=true"生效；**不动 LLM 实体提取的 is_static 覆盖路径**（171-189 行，语义判断保留现状，避免误伤"长期事实"）
- 风险：agent 有意存 learned-pattern static（防崩纪律）会被自动降级——若用户希望这类规则仍进画像，此步跳过，只做 3.1 提示

## 4. 第三步：定期健康检查（维护）

脚本/任务（可 cron 或手动）每周扫描用户容器 static：
1. 非 preference static（违反原则）→ 提示降级
2. 重复（≥0.95）→ 提示 forget
3. 过期风险（易变信息：key/地址/主机名/版本）→ 提示确认
输出报告，人工确认后执行（可恢复，forget 软删）。

## 5. 不做（尊重 Oracle 裁定）

- ❌ 读取侧预算制/截断（"行为规则永不截断"是测试锁定设计）
- ❌ difflib 去重（短中文串误伤风险）
- ❌ query 相关性过滤（无条件指令）
- ❌ 改注入机制（画像/记忆独立 cap 是正确的）

## 6. 执行顺序与影响

1. 画像净化（今天）——立竿见影，可回滚
2. 写入侧约束 3.1（本周）——防复发，一行提示
3. 健康检查脚本（下周）——维护
4. 3.2 强制降级——待用户拍板（影响"防崩纪律"类规则是否留画像）

影响：画像变纯、体积降 70%、无知识损失（降级仍可召回）；写入侧提示防项目内容再混入；全部可回滚。
