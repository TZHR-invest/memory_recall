# Phase 1 实施步骤：数据库迁移 + 基础存储服务

> **目标**：创建新表结构，实现基础存储服务
> **预估时间**：1 周

---

## 1. 前置准备

### 1.1 环境检查
- [ ] PostgreSQL 数据库运行正常
- [ ] pgvector 扩展已安装
- [ ] 现有迁移脚本已执行

### 1.2 目录结构
```
apps/api/
├── migrations/
│   └── 015_create_lossless_tables.sql  # 新增
├── src/
│   ├── services/
│   │   └── lossless/                    # 新增目录
│   │       ├── __init__.py
│   │       ├── raw_message_store.py
│   │       ├── summary_store.py
│   │       ├── context_store.py
│   │       └── dag_manager.py
│   └── models/
│       └── lossless.py                  # 新增
└── tests/
    └── test_lossless/                   # 新增目录
        ├── __init__.py
        ├── test_raw_message_store.py
        ├── test_summary_store.py
        └── test_context_store.py
```

---

## 2. 迁移脚本实现

### 2.1 任务：创建迁移脚本

**文件**：`apps/api/migrations/015_create_lossless_tables.sql`

**内容**：
1. 创建 raw_messages 表
2. 创建 summaries 表
3. 创建 summary_messages 表
4. 创建 summary_parents 表
5. 创建 summary_entities 表
6. 创建 context_items 表
7. 扩展 entities 表索引

**验证标准**：
- [ ] 所有表创建成功
- [ ] 索引创建成功
- [ ] 外键约束正确

---

## 3. 存储服务实现

### 3.1 任务：创建数据模型

**文件**：`apps/api/src/models/lossless.py`

**内容**：
- RawMessage 数据类
- Summary 数据类
- ContextItem 数据类

### 3.2 任务：实现 RawMessageStore

**文件**：`apps/api/src/services/lossless/raw_message_store.py`

**方法**：
| 方法 | 说明 |
|------|------|
| `store()` | 存储原始消息 |
| `get_by_id()` | 获取单条消息 |
| `get_by_session()` | 获取会话消息列表 |
| `get_by_document()` | 获取文档分段列表 |
| `update_embedding()` | 更新向量嵌入 |
| `get_fresh_tail()` | 获取 fresh tail |
| `estimate_tokens()` | 估算 token 数 |

**验证标准**：
- [ ] store() 返回正确的 ID
- [ ] get_by_id() 返回完整数据
- [ ] get_by_session() 按时间排序
- [ ] update_embedding() 更新成功

### 3.3 任务：实现 SummaryStore

**文件**：`apps/api/src/services/lossless/summary_store.py`

**方法**：
| 方法 | 说明 |
|------|------|
| `create_summary()` | 创建摘要节点 |
| `get_summary()` | 获取摘要 |
| `link_message()` | 关联消息 |
| `link_parent()` | 关联父摘要 |
| `link_entity()` | 关联实体 |
| `get_summary_messages()` | 获取关联消息 |
| `get_summary_parents()` | 获取父摘要 |
| `get_summary_subtree()` | 获取 DAG 子树 |

**验证标准**：
- [ ] create_summary() 返回正确 ID
- [ ] link_message() 正确建立关联
- [ ] get_summary_subtree() 递归查询正确

### 3.4 任务：实现 ContextStore

**文件**：`apps/api/src/services/lossless/context_store.py`

**方法**：
| 方法 | 说明 |
|------|------|
| `append_message()` | 追加消息 |
| `append_summary()` | 追加摘要 |
| `get_context_items()` | 获取有序序列 |
| `replace_range_with_summary()` | 替换范围为摘要 |
| `get_token_count()` | 获取 token 总数 |
| `exists()` | 检查上下文是否存在 |

**验证标准**：
- [ ] append_message() ordinal 正确递增
- [ ] get_context_items() 按 ordinal 排序
- [ ] replace_range_with_summary() 正确替换

---

## 4. 测试验证

### 4.1 单元测试

**文件**：`apps/api/tests/test_lossless/test_raw_message_store.py`

**测试用例**：
```python
test_store_raw_message()
test_get_by_id()
test_get_by_session()
test_get_by_document()
test_update_embedding()
test_fresh_tail_protection()
```

**文件**：`apps/api/tests/test_lossless/test_summary_store.py`

**测试用例**：
```python
test_create_summary()
test_link_message()
test_link_parent()
test_get_summary_subtree()
```

**文件**：`apps/api/tests/test_lossless/test_context_store.py`

**测试用例**：
```python
test_append_message()
test_append_summary()
test_replace_range()
test_get_token_count()
```

### 4.2 集成验证

**步骤**：
1. 执行迁移脚本
2. 运行单元测试
3. 手动验证表结构
4. 验证与现有系统的兼容性

---

## 5. 执行顺序

```
Step 1: 创建迁移脚本
    ↓
Step 2: 执行迁移脚本（在测试环境）
    ↓
Step 3: 创建数据模型
    ↓
Step 4: 实现 RawMessageStore
    ↓
Step 5: 编写 RawMessageStore 测试
    ↓
Step 6: 实现 SummaryStore
    ↓
Step 7: 编写 SummaryStore 测试
    ↓
Step 8: 实现 ContextStore
    ↓
Step 9: 编写 ContextStore 测试
    ↓
Step 10: 运行所有测试，验证通过
```

---

## 6. 验收标准

| 标准 | 验证方法 |
|------|----------|
| 所有表创建成功 | `\d raw_messages` 等 |
| 所有索引创建成功 | `\di` 查看索引 |
| RawMessageStore 测试通过 | `pytest tests/test_lossless/test_raw_message_store.py` |
| SummaryStore 测试通过 | `pytest tests/test_lossless/test_summary_store.py` |
| ContextStore 测试通过 | `pytest tests/test_lossless/test_context_store.py` |
| 与现有系统兼容 | 现有 API 仍然正常工作 |
