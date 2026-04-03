# Memory Recall 部署文档

> 版本: v1  
> 更新时间: 2026-03-20

## 系统要求

### 硬件要求

- CPU: 2 核+
- 内存: 4GB+
- 存储: 20GB+

### 软件要求

- 操作系统: Ubuntu 20.04+ / CentOS 8+ / macOS
- Python: 3.10+
- PostgreSQL: 14+ (with pgvector 扩展)
- Git

---

## 安装步骤

### 1. 克隆项目

```bash
cd /path/to/workspace
git clone <repository_url> memory_recall
cd memory_recall
```

### 2. 安装系统依赖

**Ubuntu/Debian:**

```bash
# 安装 PostgreSQL
sudo apt-get update
sudo apt-get install -y postgresql postgresql-contrib

# 安装 pgvector 扩展
sudo apt-get install -y postgresql-14-pgvector

# 安装 Python 开发包
sudo apt-get install -y python3-dev python3-venv
```

**macOS:**

```bash
# 安装 PostgreSQL
brew install postgresql@14

# 安装 pgvector
brew install pgvector
```

### 3. 配置数据库

```bash
# 启动 PostgreSQL
sudo systemctl start postgresql

# 创建数据库用户
sudo -u postgres createuser -s memory_user

# 创建数据库
sudo -u postgres createdb -O memory_user memory_recall

# 启用 pgvector 扩展
sudo -u postgres psql -d memory_recall -c "CREATE EXTENSION vector;"
```

### 4. 创建虚拟环境

```bash
cd apps/api
python3 -m venv venv
source venv/bin/activate
```

### 5. 安装 Python 依赖

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 6. 配置环境变量

创建 `.env` 文件：

```bash
# 应用配置
APP_NAME=Memory Recall API
APP_VERSION=1.0.0
APP_DEBUG=false

# 数据库配置
DATABASE_URL=postgresql://memory_user@localhost:5432/memory_recall

# 火山引擎 API
VOLC_API_KEY=your_api_key_here

# 服务器配置
HOST=0.0.0.0
PORT=8000
```

### 7. 初始化数据库

```bash
# 执行数据库初始化脚本（使用 schema.sql）
python init_db.py
```

**注意**：新环境使用 `schema.sql` 直接创建数据库结构，不再需要运行迁移脚本。

---

## 启动服务

### 开发模式

```bash
# 激活虚拟环境
source venv/bin/activate

# 启动服务（自动重载）
python3 -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### 生产模式

**方式 1: 直接启动**

```bash
# 激活虚拟环境
source venv/bin/activate

# 设置环境变量
export VOLC_API_KEY=your_api_key_here

# 启动服务
nohup python3 -m uvicorn main:app --host 0.0.0.0 --port 8000 > /var/log/memory_recall/api.log 2>&1 &
```

**方式 2: 使用 Gunicorn + Uvicorn**

```bash
# 安装 Gunicorn
pip install gunicorn

# 启动服务（多进程）
gunicorn main:app \
  --workers 4 \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000 \
  --access-logfile /var/log/memory_recall/access.log \
  --error-logfile /var/log/memory_recall/error.log
```

**方式 3: 使用 Systemd（推荐）**

创建服务文件 `/etc/systemd/system/memory_recall.service`:

```ini
[Unit]
Description=Memory Recall API
After=network.target postgresql.service

[Service]
Type=simple
User=memory_user
Group=memory_user
WorkingDirectory=/path/to/memory_recall/apps/api
Environment="PATH=/path/to/memory_recall/apps/api/venv/bin"
Environment="VOLC_API_KEY=your_api_key_here"
ExecStart=/path/to/memory_recall/apps/api/venv/bin/python3 -m uvicorn main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

启动服务：

```bash
# 重载 systemd
sudo systemctl daemon-reload

# 启动服务
sudo systemctl start memory_recall

# 设置开机启动
sudo systemctl enable memory_recall

# 查看状态
sudo systemctl status memory_recall
```

---

## 健康检查

```bash
# 检查服务状态
curl http://localhost:8000/health

# 预期输出
{"status":"healthy","app":"Memory Recall API","version":"1.0.0"}
```

---

## 性能优化

### 1. 数据库优化

```sql
-- 索引已在 schema.sql 中创建，无需单独执行
-- 如需手动添加索引，参考 schema.sql 中的 CREATE INDEX 语句

-- 配置连接池
ALTER SYSTEM SET max_connections = 200;
ALTER SYSTEM SET shared_buffers = '256MB';
```

### 2. 应用优化

- Embedding 缓存: 默认 1000 条，可在代码中调整
- 并发处理: 自动并发执行向量存储和图谱构建
- 批量处理: 使用 `batch_create_memories` 方法

### 3. 服务器优化

```bash
# 增加文件描述符限制
ulimit -n 65535

# 优化内核参数
sudo sysctl -w net.core.somaxconn=1024
sudo sysctl -w net.ipv4.tcp_max_syn_backlog=1024
```

---

## 监控与日志

### 日志位置

- API 日志: `/var/log/memory_recall/api.log`
- 访问日志: `/var/log/memory_recall/access.log`
- 错误日志: `/var/log/memory_recall/error.log`

### 查看日志

```bash
# 实时查看日志
tail -f /var/log/memory_recall/api.log

# 查看错误日志
grep ERROR /var/log/memory_recall/api.log
```

---

## 故障排查

### 1. 数据库连接失败

```bash
# 检查 PostgreSQL 状态
sudo systemctl status postgresql

# 检查连接
psql -h localhost -U memory_user -d memory_recall
```

### 2. API 启动失败

```bash
# 检查端口占用
lsof -i :8000

# 检查日志
tail -100 /var/log/memory_recall/error.log
```

### 3. Embedding 生成失败

```bash
# 检查 API Key
echo $VOLC_API_KEY

# 测试 API 连接
curl -s https://ark.cn-beijing.volces.com/api/v3/embeddings \
  -H "Authorization: Bearer $VOLC_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"input": "test", "model": "doubao-embedding"}'
```

---

## 备份与恢复

### 备份数据库

```bash
# 全量备份
pg_dump -U memory_user memory_recall > backup_$(date +%Y%m%d).sql

# 仅数据备份
pg_dump -U memory_user --data-only memory_recall > data_backup.sql
```

### 恢复数据库

```bash
# 恢复数据
psql -U memory_user -d memory_recall < backup_20260320.sql
```

---

## 安全建议

1. **修改默认端口**: 避免使用 8000 端口
2. **启用 HTTPS**: 使用 Nginx 反向代理
3. **限制数据库访问**: 仅允许本地连接
4. **定期备份**: 每日自动备份
5. **监控日志**: 设置日志告警
