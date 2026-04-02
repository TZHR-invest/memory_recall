# 最新更新总结与重启指南

## 已完成的更新

### 1. Web 端 `/recall` 端点

**修改文件**: `routes/memories.py`

**变更内容**:
- ✅ 默认使用智能召回（Function Calling）
- ✅ 新增 `use_smart_recall` 参数（默认 `true`）
- ✅ 新增 `route_decision` 返回字段
- ✅ 图谱召回失败自动降级

### 2. 关系类型优化

**修改文件**: `graph_tools.py`, `prompts.py`

**变更内容**:
- ✅ 添加 `classmate`（同学）关系类型
- ✅ 添加 7 个新关系类型
- ✅ 更新 Prompt 示例

### 3. 图谱召回降级机制

**修改文件**: `smart_recall_service.py`

**变更内容**:
- ✅ 图谱召回失败自动降级到混合召回
- ✅ 返回 `fallback_used` 标记

---

## 重启步骤

### 开发环境

```bash
# 1. 停止当前服务
Ctrl+C

# 2. 重启 API
cd apps/api
python -m uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

### Docker 环境

```bash
# 1. 重启容器
docker-compose restart api

# 或重新构建
docker-compose up -d --build api
```

### 生产环境

```bash
# 1. 拉取最新代码
git pull

# 2. 重启服务
systemctl restart memory-recall-api

# 或使用 supervisor
supervisorctl restart memory-recall-api
```

---

## 验证更新

### 1. 测试智能召回

```bash
curl -X POST http://localhost:8000/api/v1/memories/recall \
  -H "Content-Type: application/json" \
  -d '{
    "query": "张三的朋友",
    "user_id": "test_user",
    "limit": 10
  }'
```

**预期响应**:
```json
{
  "code": 200,
  "data": {
    "answer": "...",
    "recall_mode": "smart_recall",  // ✅ 智能召回
    "route_decision": {
      "strategy": "graph_recall",     // ✅ 决策信息
      "reason": "查询涉及人物关系"
    }
  }
}
```

### 2. 测试关系提取

```bash
# 创建记忆（会提取 classmate 关系）
curl -X POST http://localhost:8000/api/v1/memories \
  -H "Content-Type: application/json" \
  -d '{
    "content": "我和张三李四都是大学同学",
    "user_id": "test_user"
  }'
```

**预期结果**:
- ✅ 提取 `classmate` 关系（不是 `related_to`）

---

## 修改文件清单

| 文件 | 修改内容 | 是否需要重启 |
|------|---------|------------|
| `routes/memories.py` | 智能召回集成 | ✅ 是 |
| `smart_recall_service.py` | 降级机制 | ✅ 是 |
| `graph_tools.py` | 关系类型 | ✅ 是 |
| `prompts.py` | Prompt 更新 | ✅ 是 |
| `enhanced_entity_extractor.py` | 实体匹配增强 | ✅ 是 |
| `graph_recall_service.py` | Auto 模式 | ✅ 是 |

---

## 检查清单

重启前确认：

- [ ] 所有文件已保存
- [ ] 数据库迁移已完成（如果有）
- [ ] 依赖已安装（如果有新依赖）
- [ ] 配置文件已更新（如果有）

重启后验证：

- [ ] API 正常启动
- [ ] `/recall` 端点返回 `recall_mode` 字段
- [ ] `/recall` 端点返回 `route_decision` 字段
- [ ] 关系提取使用 `classmate`（不是 `related_to`）

---

## 快速重启命令

```bash
# 开发环境（推荐）
cd apps/api && python -m uvicorn src.main:app --reload

# 或者使用 make
make restart-api

# 或者使用脚本
./scripts/restart.sh
```

---

## 常见问题

### Q: 不重启会怎样？

**A**: 代码修改不会生效，API 仍使用旧逻辑。

### Q: 重启会影响现有数据吗？

**A**: 不会，只影响代码逻辑，数据库数据不变。

### Q: 如何确认更新已生效？

**A**: 检查响应中是否包含新字段：
- `recall_mode`: 智能召回标识
- `route_decision`: 决策信息
- `fallback_used`: 降级标记

---

## 总结

| 问题 | 答案 |
|------|------|
| Web 端是否最新？ | ✅ 是，已集成智能召回 |
| 需要重启吗？ | ✅ **是，必须重启** |
| 重启后验证什么？ | `recall_mode` 和 `route_decision` 字段 |
