# Memory Recall - Web 前端使用指南

## 🚀 快速启动

### 方式 1：一键启动（推荐）

```bash
# 在项目根目录执行
./web/server.sh
```

### 方式 2：手动启动

```bash
# 1. 启动 API 服务（如果还没运行）
cd /home/wbaifan/.openclaw/workspace-ai_tui/projects/memory_recall
python3 -m uvicorn apps.api.main:app --host 0.0.0.0 --port 8000

# 2. 启动前端服务
cd web
python3 -m http.server 3000
```

### 方式 3：指定端口

```bash
./web/server.sh 8080
# 或
python3 -m http.server 8080
```

## 📱 访问地址

启动后，打开浏览器访问：

- **前端界面**：http://localhost:3000
- **API 文档**：http://localhost:8000/docs
- **健康检查**：http://localhost:8000/health

## 🎯 功能使用

### 1. 首页

**统计信息**：
- 总记忆数：显示数据库中的记忆总数
- 今日新增：今天创建的记忆数量
- 本周新增：本周创建的记忆数量

**快速创建**：
1. 在文本框中输入记忆内容
2. 点击"创建记忆"按钮
3. 等待 Toast 通知提示成功

**最近记忆**：
- 显示最近 5 条记忆
- 点击可查看详情

### 2. 创建记忆

**详细创建**：
1. 点击导航栏的"创建记忆"
2. 输入记忆内容（必填）
3. 选择输入类型（文本/对话/笔记）
4. 添加标签（可选，逗号分隔）
5. 点击"创建记忆"按钮

**标签格式**：
```
生活, 社交, 咖啡店
```

### 3. 记忆列表

**查看列表**：
1. 点击导航栏的"记忆列表"
2. 查看所有记忆（分页显示，每页 10 条）

**关键词过滤**：
1. 在搜索框中输入关键词
2. 点击"过滤"按钮
3. 查看匹配的记忆

**分页导航**：
- 点击页码跳转
- 点击"上一页"/"下一页"翻页

**查看详情**：
- 点击任意记忆条目
- 在模态框中查看完整信息

### 4. 语义搜索

**自然语言查询**：
1. 点击导航栏的"搜索"
2. 输入自然语言查询，例如：
   - "最近见过的朋友"
   - "关于咖啡的记忆"
   - "开心的事情"
3. 选择结果数量（5/10/20 条）
4. 点击"搜索"按钮

**相关度评分**：
- 每条结果显示相关度百分比
- 百分比越高，匹配度越高

### 5. 统计页面

**详细统计**：
- 总记忆数
- 今日新增
- 本周新增
- 本月新增
- 数据库状态
- 缓存状态

## ⌨️ 快捷键

- `ESC` - 关闭模态框

## 🎨 UI 说明

### 颜色主题

- **主色**：渐变紫色（#667eea → #764ba2）
- **背景**：白色卡片
- **文字**：深灰色（#333）
- **强调**：紫色（#667eea）

### 交互反馈

- **Toast 通知**：绿色（成功）、红色（错误）、灰色（信息）
- **加载状态**：旋转动画
- **悬停效果**：卡片上浮 + 阴影

### 响应式设计

- **桌面端**：最大宽度 1200px
- **移动端**：自适应布局
- **字体大小**：根据屏幕调整

## 🔧 故障排查

### 问题 1：前端无法访问

**症状**：浏览器无法打开 http://localhost:3000

**解决**：
```bash
# 检查端口是否被占用
lsof -i:3000

# 使用其他端口
python3 -m http.server 8080
```

### 问题 2：API 调用失败

**症状**：Toast 提示"请求失败"

**解决**：
```bash
# 1. 检查 API 服务状态
curl http://localhost:8000/health

# 2. 检查浏览器控制台（F12）
# 3. 查看 CORS 错误

# 4. 确认 API_BASE 配置
# 在 index.html 中检查：
# const API_BASE = 'http://localhost:8000';
```

### 问题 3：记忆列表为空

**症状**：列表显示"没有找到记忆"

**解决**：
```bash
# 1. 检查数据库
curl http://localhost:8000/api/v1/memories?limit=5

# 2. 创建测试数据
curl -X POST http://localhost:8000/api/v1/memories \
  -H "Content-Type: application/json" \
  -d '{"content": "测试记忆", "input_type": "text"}'
```

### 问题 4：搜索无结果

**症状**：语义搜索返回空结果

**解决**：
```bash
# 1. 确认有数据
curl http://localhost:8000/api/v1/memories?limit=5

# 2. 检查 Embedding 生成
curl http://localhost:8000/api/stats

# 3. 查看浏览器控制台错误
```

## 📊 性能优化建议

### 1. 减少请求次数

- 使用分页加载数据
- 缓存常用数据

### 2. 提升加载速度

- 使用 CDN 加速（生产环境）
- 压缩静态资源

### 3. 改善用户体验

- 添加骨架屏
- 使用虚拟滚动（大量数据时）

## 🚀 部署建议

### 本地开发

```bash
python3 -m http.server 3000
```

### 生产部署

**Nginx 配置**：
```nginx
server {
    listen 80;
    server_name memory-recall.example.com;
    
    location / {
        root /path/to/memory_recall/web;
        index index.html;
        try_files $uri $uri/ /index.html;
    }
    
    location /api {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

**Docker 部署**：
```dockerfile
FROM nginx:alpine
COPY web/ /usr/share/nginx/html/
EXPOSE 80
```

## 📝 开发说明

### 修改 API 地址

编辑 `web/index.html`：

```javascript
const API_BASE = 'http://localhost:8000';
```

### 自定义样式

编辑 `<style>` 标签内的 CSS：

```css
body {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
}
```

### 添加新功能

1. 在 HTML 中添加页面结构
2. 在 JavaScript 中添加逻辑
3. 测试 API 集成

---

**最后更新**：2026-03-19  
**维护者**：颓弟
