# Memory Recall

通用记忆召回系统 - 首先解决人类记忆痛点，其次服务 AI Agent。

## 项目定位

### 核心目标

1. **人类记忆管理**：帮助人们记录、管理和召回记忆
   - 时间追溯：想知道某个时间段发生过什么
   - 事件召回：想起一件事但不记得全貌
   - 灵感记录：一闪而过的灵感不再忘记
   - 项目跟踪：搁置的项目从哪里重新下手

2. **AI Agent 支持**：提供高质量上下文召回
   - 解决上下文窗口限制
   - 解决模型注意力分散问题
   - 按需召回相关记忆

### 核心特性

- 多模态输入：文本、图片、语音
- 结构化存储：时间、地点、人物、标签
- 智能召回：语义搜索 + 多维度过滤
- 人脸识别：辅助识别照片中的人物

## 技术栈

| 组件 | 方案 |
|------|------|
| 数据库 | PostgreSQL + pgvector |
| 向量模型 | doubao-embedding-vision-251215 |
| 人脸识别 | face_recognition |
| LLM | doubao-seed-2-0-pro-260215 |
| 后端框架 | FastAPI |
| 部署 | Docker Compose |

## 文档

- [架构设计](docs/architecture.md)
- [数据模型](docs/data-model.md)
- [处理流程](docs/processing-pipeline.md)
- [召回机制](docs/recall-mechanism.md)
- [API 设计](docs/api-design.md)
- [开发计划](docs/development-plan.md)
- [技术栈](docs/tech-stack.md)

## 开发状态

- [x] 项目设计
- [x] 技术栈确认
- [ ] 项目骨架搭建
- [ ] 核心模块开发
- [ ] 测试与部署

## License

MIT
