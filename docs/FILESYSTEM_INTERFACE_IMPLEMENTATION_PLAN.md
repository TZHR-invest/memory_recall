# memory_recall 文件系统接口实现方案

> **创建时间**：2026-03-21 04:51  
> **目标**：为 memory_recall 实现文件系统接口，提升 Agent 操作效率 10 倍

---

## 📊 背景分析

### 当前问题

**memory_recall 当前只有 RESTful API**：
- Agent 必须通过 HTTP 调用
- 无法使用现有工具链（grep、sed、awk、编辑器）
- 操作效率低，学习成本高

**db9.ai 的优势**：
- 文件系统 + SQL 融合接口
- Agent 可以像操作文件一样操作数据
- 无缝集成现有工具链

### 解决方案

为 memory_recall 实现文件系统接口（基于 FUSE），让 Agent 可以：
- 用 `cat`、`vim`、`grep` 等工具操作记忆
- 用 Git 管理记忆版本
- 用 `find`、`rg` 搜索记忆

---

## 🎯 设计目标

### 核心目标

| 目标 | 说明 |
|------|------|
| **提升效率** | Agent 操作效率提升 10 倍 |
| **兼容现有工具** | 支持所有文件操作工具 |
| **保持精度** | 不影响记忆召回精度 |
| **易于使用** | 学习成本接近零 |

### 设计原则

1. **文件系统优先**：主要用文件系统，API 作为补充
2. **只读 + 读写分离**：先实现只读，再实现读写
3. **Markdown 友好**：记忆内容以 Markdown 格式存储
4. **性能优化**：缓存常用记忆，减少数据库查询

---

## 🏗️ 技术方案

### 方案选择

| 方案 | 优点 | 缺点 | 选择 |
|------|------|------|------|
| **FUSE** | 成熟、跨平台、Python 支持 | 需要 root 权限 | ✅ 推荐 |
| **WebDAV** | HTTP 协议、无需 root | 性能较低 | 备选 |
| **NFS** | 标准协议 | 配置复杂 | 不推荐 |

### 技术栈

| 组件 | 选择 | 说明 |
|------|------|------|
| **FUSE 库** | `fusepy` | Python FUSE 绑定 |
| **后端存储** | PostgreSQL | 保持现有数据库 |
| **文件格式** | Markdown + YAML Front Matter | 人类可读 |

### 文件路径设计

```
~/memories/                           # 挂载点
├── 2026-03/                          # 按月份组织
│   ├── 19.md                         # 2026-03-19 的记忆
│   ├── 20.md                         # 2026-03-20 的记忆
│   └── 21.md                         # 2026-03-21 的记忆
├── people/                           # 人物记忆
│   ├── 张三.md                       # 所有提到张三的记忆
│   └── 李四.md                       # 所有提到李四的记忆
├── locations/                        # 地点记忆
│   ├── 咖啡店.md                     # 所有提到咖啡店的记忆
│   └── 公司.md                       # 所有提到公司的记忆
├── tags/                             # 标签记忆
│   ├── 工作.md                       # 所有带"工作"标签的记忆
│   └── 学习.md                       # 所有带"学习"标签的记忆
└── .search                           # 特殊文件：搜索接口
```

### 文件格式

```markdown
---
id: mem_xxx
created_at: 2026-03-19T14:30:00+08:00
people:
  - name: 张三
    role: friend
location:
  name: 咖啡店
  address: 北京市朝阳区xxx
emotion:
  value: happy
  confidence: 0.9
tags:
  - 工作
  - 项目讨论
---

# 2026-03-19 记忆

今天和老同学张三在咖啡店讨论了项目进展...

## 详细内容

（记忆的详细内容）
```

---

## 💻 实现细节

### Phase 1：只读文件系统（1 周）

**核心类设计**：

```python
from fuse import FUSE, FuseOSError, Operations
import os
import sys
import errno
from datetime import datetime

class MemoryFS(Operations):
    def __init__(self, db_connection):
        self.db = db_connection
        self.cache = {}  # 缓存常用记忆
        
    def getattr(self, path, fh=None):
        """获取文件或目录属性"""
        # 解析路径：/2026-03/19.md
        # 查询数据库获取记忆信息
        # 返回文件属性（大小、修改时间等）
        
    def readdir(self, path, fh):
        """列出目录内容"""
        # 路径：/ → 返回月份目录、people、locations、tags
        # 路径：/2026-03 → 返回该月份的所有记忆文件
        # 路径：/people → 返回所有人物记忆文件
        
    def read(self, path, size, offset, fh):
        """读取文件内容"""
        # 解析路径获取记忆 ID
        # 查询数据库获取记忆内容
        # 返回 Markdown 格式的内容
        
    def open(self, path, flags):
        """打开文件"""
        # 检查权限
        # 返回文件句柄
```

**实现步骤**：

1. **Day 1-2**：实现基础框架
   - 创建 `MemoryFS` 类
   - 实现 `getattr`、`readdir`、`read` 方法

2. **Day 3-4**：实现路径解析
   - 解析路径到数据库查询
   - 实现缓存机制

3. **Day 5-7**：测试和优化
   - 测试所有文件操作
   - 优化性能

### Phase 2：读写文件系统（1 周）

**新增方法**：

```python
def write(self, path, data, offset, fh):
    """写入文件内容"""
    # 解析 Markdown 文件
    # 提取元数据和内容
    # 更新数据库
    
def create(self, path, mode):
    """创建新文件"""
    # 创建新记忆
    
def unlink(self, path):
    """删除文件"""
    # 删除记忆
    
def mkdir(self, path, mode):
    """创建目录"""
    # 创建新分类（people、locations、tags）
```

**实现步骤**：

1. **Day 1-3**：实现写入功能
   - 实现 `write`、`create` 方法
   - Markdown 解析和验证

2. **Day 4-5**：实现删除功能
   - 实现 `unlink`、`rmdir` 方法

3. **Day 6-7**：测试和优化
   - 测试所有文件操作
   - 性能优化

### Phase 3：混合接口（3 天）

**SQL 接口设计**：

```python
# 特殊文件：.search
# 用法：echo "SELECT * FROM memories WHERE emotion = 'happy'" > .search

def read(self, path, size, offset, fh):
    if path == '/.search':
        # 执行 SQL 查询
        # 返回查询结果（Markdown 格式）
```

**实现步骤**：

1. **Day 1**：设计 SQL 接口规范
2. **Day 2**：实现 SQL 查询功能
3. **Day 3**：测试和文档

---

## 🧪 测试计划

### 单元测试

```python
# test_memory_fs.py

def test_readdir():
    """测试列出目录"""
    fs = MemoryFS(db_connection)
    files = fs.readdir('/', 0)
    assert '2026-03' in files
    assert 'people' in files
    
def test_read():
    """测试读取记忆"""
    fs = MemoryFS(db_connection)
    content = fs.read('/2026-03/19.md', 1024, 0, 0)
    assert '2026-03-19' in content
    
def test_write():
    """测试写入记忆"""
    fs = MemoryFS(db_connection)
    fs.write('/2026-03/new.md', b'# 新记忆\n内容...', 0, 0)
    # 验证数据库中是否创建了新记忆
```

### 集成测试

```bash
# 挂载文件系统
python memory_fs.py ~/memories

# 测试文件操作
ls ~/memories/
cat ~/memories/2026-03/19.md
grep "张三" ~/memories/2026-03/*.md
vim ~/memories/2026-03/new.md

# 测试 Git 管理
cd ~/memories
git init
git add .
git commit -m "Initial commit"
```

### 性能测试

| 操作 | 目标 | 实际 |
|------|------|------|
| 列出目录（100 个文件） | < 100ms | - |
| 读取文件（1KB） | < 50ms | - |
| 写入文件（1KB） | < 100ms | - |
| 搜索（grep） | < 1s | - |

---

## 📊 成本分析

### 开发成本

| 阶段 | 时间 | 人力 |
|------|------|------|
| **Phase 1（只读）** | 1 周 | 1 个后端工程师 |
| **Phase 2（读写）** | 1 周 | 1 个后端工程师 |
| **Phase 3（混合接口）** | 3 天 | 1 个后端工程师 |
| **测试和文档** | 3 天 | 1 个后端工程师 |
| **总计** | **2.5 周** | **1 个后端工程师** |

### 运行成本

| 成本项 | 说明 |
|--------|------|
| **CPU** | 可忽略（FUSE 是轻量级） |
| **内存** | 缓存常用记忆（< 100MB） |
| **存储** | 无额外存储（使用现有数据库） |
| **网络** | 无额外网络开销 |

---

## 🎯 预期效果

### 效率提升

| 操作 | API 方式 | 文件系统方式 | 提升倍数 |
|------|---------|-------------|---------|
| 浏览记忆 | `curl` + `jq` | `ls` | **10x** |
| 搜索记忆 | `curl` + 手动解析 | `grep` | **10x** |
| 编辑记忆 | API 调用 | `vim` | **5x** |
| 备份记忆 | 导出 + 下载 | `tar` | **10x** |

### 工具兼容性

| 工具 | API 支持 | 文件系统支持 |
|------|---------|-------------|
| 文本编辑器 | ❌ | ✅ |
| grep/sed/awk | ❌ | ✅ |
| Git | ❌ | ✅ |
| find/rg | ❌ | ✅ |
| 备份工具 | ❌ | ✅ |

---

## 🚀 实施路线图

### Week 1：Phase 1（只读文件系统）

| 天 | 任务 | 目标 |
|----|------|------|
| 1-2 | 实现基础框架 | `getattr`、`readdir`、`read` |
| 3-4 | 实现路径解析 | 数据库查询 + 缓存 |
| 5-7 | 测试和优化 | 所有文件操作正常 |

### Week 2：Phase 2（读写文件系统）

| 天 | 任务 | 目标 |
|----|------|------|
| 1-3 | 实现写入功能 | `write`、`create` |
| 4-5 | 实现删除功能 | `unlink`、`rmdir` |
| 6-7 | 测试和优化 | 所有文件操作正常 |

### Week 3：Phase 3（混合接口）

| 天 | 任务 | 目标 |
|----|------|------|
| 1 | 设计 SQL 接口 | 规范定义 |
| 2 | 实现 SQL 查询 | `.search` 文件 |
| 3 | 测试和文档 | 完整测试 + 文档 |

---

## 📝 相关资源

### 技术文档

- [FUSE 官方文档](https://github.com/libfuse/libfuse)
- [fusepy GitHub](https://github.com/fusepy/fusepy)
- [Python FUSE 教程](https://www.stavros.io/posts/python-fuse-filesystem/)

### 参考项目

- [Python-FUSE-Sample](https://github.com/skorokithakis/python-fuse-sample)
- [db9.ai 分析报告](./MEMORY_RECALL_VS_DB9_ANALYSIS.md)

---

## 💡 关键认知

### 1. 文件系统接口是 Agent 的"第一语言"

Agent 的工具链基于文件系统：
- 代码仓库都是文件
- 文档系统都是文件
- 日志系统都是文件

提供文件系统接口，Agent 可以无缝使用现有工具链。

### 2. 只读 + 读写分离

先实现只读文件系统（1 周），验证效果后再实现读写（1 周）。

**原因**：
- 只读实现简单，风险低
- 可以快速验证效果
- 根据反馈调整设计

### 3. Markdown 友好

记忆内容以 Markdown 格式存储，人类可读。

**原因**：
- Markdown 是通用格式
- 可以直接用编辑器查看
- 可以用 Git 管理

### 4. 性能优化

使用缓存减少数据库查询。

**策略**：
- 缓存常用记忆
- 缓存目录列表
- 定期刷新缓存

---

**创建时间**：2026-03-21 04:51  
**预计完成**：2026-04-05  
**负责人**：颓弟 AI Agent  
**状态**：规划完成，待实施
