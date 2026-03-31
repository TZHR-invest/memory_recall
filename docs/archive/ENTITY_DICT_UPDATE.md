# 实体词典实时更新机制

## 问题背景

**原始问题**：实体词典在存入新实体后没有实时更新，导致用户创建记忆后立即查询不到新实体。

```
用户创建记忆 → 实体存入数据库 → 词典未更新 ❌
    ↓
用户立即查询 → 使用旧词典 → 查不到新实体 ❌
```

## 解决方案

### 三层更新机制

#### 1. 实时更新（主要）

**位置**：`graph_builder_service.py:537-548`

```python
async def _upsert_entity(self, name, entity_type, user_id, confidence):
    # 存入数据库
    entity_id = await db.fetchrow("INSERT INTO entities ...")
    
    # ⭐ 立即更新词典
    if entity_id:
        await self._update_entity_dict(name, entity_id, entity_type, user_id, confidence)
    
    return entity_id
```

**优点**：
- ✅ 立即生效
- ✅ 性能开销小
- ✅ 保证一致性

#### 2. 定时刷新（兜底）

**位置**：`enhanced_entity_extractor.py:31-50`

```python
def __init__(self):
    self._last_refresh_time = None
    self._auto_refresh_interval = 300  # 5分钟

async def check_and_refresh(self):
    """定时检查并刷新词典"""
    elapsed = time.time() - self._last_refresh_time
    
    if elapsed > self._auto_refresh_interval:
        await self.refresh()
```

**触发时机**：
- 每次 `extract_entities()` 调用时检查
- 超过 5 分钟自动刷新

**优点**：
- ✅ 兜底机制，防止遗漏
- ✅ 保证最终一致性
- ✅ 自动修复

#### 3. 手动刷新

**位置**：`entity_dictionary_service.py:160-172`

```python
async def refresh(self):
    """手动刷新词典"""
    self._initialized = False
    self.entity_dict.clear()
    await self.initialize()
```

**使用场景**：
- 管理员手动操作
- 批量导入数据后
- 系统维护

## 实现细节

### 数据流

```
新实体入库
    ↓
① 写入数据库
    ↓
② 调用 _update_entity_dict()
    ↓
③ 更新内存词典（增量）
    ↓
④ 用户立即能查到 ✅
```

### 代码位置

| 功能 | 文件 | 行号 |
|------|------|------|
| 实体存储 | `graph_builder_service.py` | 481-548 |
| 词典更新 | `graph_builder_service.py` | 549-569 |
| 定时检查 | `enhanced_entity_extractor.py` | 31-50 |
| 手动刷新 | `entity_dictionary_service.py` | 160-172 |

### 关键方法

#### 1. 增量更新

```python
async def _update_entity_dict(self, entity_name, entity_id, entity_type, user_id, confidence):
    """增量更新词典"""
    self.entity_dict.add_entity(entity_name, {
        "id": entity_id,
        "type": entity_type,
        "confidence": confidence,
        "user_id": user_id
    })
    
    logger.info(f"✅ 实体词典已更新: {entity_name}")
```

#### 2. 全量刷新

```python
async def refresh(self):
    """全量刷新词典"""
    self._initialized = False
    self.entity_dict.clear()
    await self.initialize()
    
    logger.info(f"实体词典刷新完成，共 {len(self.entity_dict)} 个实体")
```

#### 3. 自动检查

```python
def extract_entities(self, query, user_id, methods):
    # 自动检查刷新
    asyncio.create_task(self.check_and_refresh())
    
    # 提取实体
    ...
```

## 测试验证

### 测试用例

```python
# 1. 创建新实体
entity_id = await graph_builder._upsert_entity(
    name="测试实体",
    entity_type="topic",
    user_id="test_user"
)

# 2. 立即查询
entities = entity_dict.extract_entities_fast("测试实体", "test_user")

# 3. 验证结果
assert "测试实体" in entities  # ✅ 应该能找到
```

### 运行测试

```bash
cd apps/api
python tests/test_dict_update.py
```

## 性能影响

### 实时更新

- **耗时**：< 1ms（内存操作）
- **影响**：几乎无

### 定时刷新

- **耗时**：50-200ms（数据库查询）
- **频率**：每 5 分钟
- **影响**：可忽略

## 注意事项

### 1. 双词典同步

**问题**：存在两个词典实例
- `EntityDictionaryService`
- `EnhancedEntityExtractor`

**解决**：共享词典引用

```python
# 同步词典
enhanced_extractor.entity_dict = entity_dict.entity_dict
```

### 2. 实体删除

**问题**：删除实体时也需要从词典中移除

**解决**：

```python
async def delete_entity(entity_name):
    # 从数据库删除
    await db.execute("DELETE FROM entities WHERE name = $1", entity_name)
    
    # 从词典中移除
    entity_dict.remove_entity(entity_name)
```

### 3. 分布式环境

**问题**：多实例部署时词典不同步

**解决方案**：

#### 方案 1：Redis 共享缓存

```python
import redis

# 使用 Redis 作为共享词典
redis_client = redis.Redis(host='localhost', port=6379, db=0)

# 存储实体
redis_client.hset('entity_dict', entity_name, json.dumps(entity_info))

# 读取实体
entity_info = redis_client.hget('entity_dict', entity_name)
```

#### 方案 2：消息队列通知

```python
# 实体变更时发送消息
await mq.publish('entity_update', {
    'action': 'add',
    'entity_name': entity_name,
    'entity_info': entity_info
})

# 其他实例订阅消息
async def handle_entity_update(message):
    if message['action'] == 'add':
        entity_dict.add_entity(message['entity_name'], message['entity_info'])
```

#### 方案 3：数据库轮询

```python
# 定期检查数据库变更
async def check_entity_changes():
    last_check_time = get_last_check_time()
    
    # 查询新增实体
    new_entities = await db.fetch(
        "SELECT * FROM entities WHERE created_at > $1",
        last_check_time
    )
    
    # 更新词典
    for entity in new_entities:
        entity_dict.add_entity(entity.name, entity)
```

## 最佳实践

### 1. 优先使用实时更新

```python
# ✅ 推荐：实时更新
entity_id = await graph_builder._upsert_entity(...)
# 词典自动更新

# ❌ 不推荐：手动刷新
await entity_dict.refresh()  # 性能开销大
```

### 2. 定时刷新作为兜底

```python
# 配置合理的刷新间隔
self._auto_refresh_interval = 300  # 5分钟

# 根据数据量调整
# - 小数据量（< 1000）：5分钟
# - 中数据量（1000-10000）：10分钟
# - 大数据量（> 10000）：30分钟
```

### 3. 监控词典状态

```python
# 记录词典统计信息
stats = entity_dict.get_stats()
logger.info(f"词典统计: {stats}")

# 监控指标：
# - 实体数量
# - 刷新次数
# - 更新次数
```

## 总结

### 核心价值

1. **实时性**：新实体立即可查
2. **一致性**：定时刷新保证最终一致性
3. **性能**：增量更新开销小
4. **可靠性**：多层机制保证

### 推荐配置

```python
# 生产环境推荐
- 实时更新: ✅ 启用
- 定时刷新: ✅ 启用（5分钟）
- 手动刷新: ✅ 提供 API
- 监控告警: ✅ 记录日志
```

### 未来优化

- [ ] Redis 共享词典（分布式）
- [ ] 消息队列通知（实时同步）
- [ ] 增量同步机制（减少开销）
- [ ] 监控大盘（可视化）
