# Memory Recall Web Frontend

基于纯 HTML + JavaScript 的单页面 Web 应用，无需构建工具。

## 快速开始

### 1. 启动 API 服务

确保后端 API 服务正在运行：

```bash
cd /home/wbaifan/.openclaw/workspace-ai_tui/projects/memory_recall
python3 -m uvicorn apps.api.main:app --reload --host 0.0.0.0 --port 8000
```

### 2. 启动前端服务

```bash
cd web
python3 -m http.server 3000
# 或使用启动脚本
./server.sh 3000
```

### 3. 访问应用

打开浏览器访问：http://localhost:3000

## 功能列表

### 🏠 首页
- 系统统计（总记忆数、今日新增、本周新增）
- 快速创建记忆
- 最近记忆列表

### ➕ 创建记忆
- 支持文本、对话、笔记三种类型
- 自定义标签

### 📋 记忆列表
- 分页展示
- 关键词过滤
- 点击查看详情

### 🔍 语义搜索
- 自然语言查询
- 相关度评分
- 可选结果数量

### 📊 统计页面
- 详细统计数据
- 缓存状态展示

## 技术栈

- **HTML5** - 页面结构
- **CSS3** - 样式设计（渐变、动画、响应式）
- **JavaScript (ES6+)** - 业务逻辑
- **Fetch API** - HTTP 请求

## API 端点

前端调用的 API 端点：

```
POST   /api/v1/memories          # 创建记忆
GET    /api/v1/memories          # 列出记忆
GET    /api/v1/memories/{id}     # 获取详情
DELETE /api/v1/memories/{id}     # 删除记忆
POST   /api/v1/memories/search   # 搜索记忆
GET    /health                   # 健康检查
GET    /api/stats                # 统计信息
```

## 文件结构

```
web/
├── index.html    # 单页面应用（包含 HTML + CSS + JavaScript）
├── server.sh     # 启动脚本
└── README.md     # 本文件
```

## 特性

### 🎨 UI 设计
- 渐变紫色主题
- 卡片式布局
- 平滑动画效果
- 响应式设计（适配移动端）

### ✨ 交互体验
- Toast 通知提示
- 加载状态显示
- 键盘快捷键（ESC 关闭模态框）
- 点击外部关闭模态框

### 🔧 技术特点
- 纯前端实现，无需构建
- 单文件应用，易于部署
- RESTful API 集成
- 完整的错误处理

## 浏览器支持

- Chrome/Edge (推荐)
- Firefox
- Safari
- 其他现代浏览器

## 故障排查

### 前端无法访问 API

1. 检查 API 服务是否运行：访问 http://localhost:8000/health
2. 检查浏览器控制台是否有 CORS 错误
3. 确认 `API_BASE` 配置正确（在 `index.html` 中）

### 记忆列表为空

1. 确认数据库中有数据
2. 检查 API 响应：访问 http://localhost:8000/api/v1/memories?limit=5
3. 查看浏览器控制台错误信息

## 开发计划

- [ ] 添加用户认证
- [ ] 支持图片上传
- [ ] 导出数据功能
- [ ] 批量操作
- [ ] 高级筛选
- [ ] 时间线视图

---

**开发时间**：2026-03-19  
**技术栈**：纯 HTML + JavaScript  
**状态**：✅ 已完成
