# 贡献指南

感谢你考虑为 Memory Recall 贡献代码！

## 🐛 报告 Bug

1. 搜索 [Issues](https://github.com/TZHR-invest/memory_recall/issues) 确认是否已有人报告
2. 如果不存在，[新建 Issue](https://github.com/TZHR-invest/memory_recall/issues/new)
3. 标题清晰描述问题
4. 内容包含：复现步骤、期望行为、实际行为、环境信息（Python 版本、OS、数据库版本）

## 💡 请求功能

同样通过 Issues 提交，标签 `enhancement`。描述你的使用场景和期望效果。

## 🔧 提交 PR

### 流程

1. Fork 本仓库
2. 创建分支：`git checkout -b feat/your-feature`（功能）或 `fix/your-fix`（修复）
3. 提交代码
4. 运行测试，确保通过
5. 推送并创建 PR

### 开发环境

```bash
cd apps/api
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 运行测试
pytest
```

### 代码规范

- **Python**: 遵循 PEP 8，使用 `ruff` 检查
- **TypeScript**: 遵循项目现有风格
- **提交信息**: 遵循 [Conventional Commits](https://www.conventionalcommits.org/)
  - `feat:` 新功能
  - `fix:` Bug 修复
  - `docs:` 文档
  - `refactor:` 重构
  - `chore:` 构建/工具

### PR 检查清单

- [ ] 代码通过 lint 检查
- [ ] 测试已添加/更新
- [ ] 文档已更新（如果需要）
- [ ] Commit 信息清晰且遵循规范

## 📋 分支说明

| 分支 | 用途 |
|------|------|
| `main` | 稳定版，从 `develop` 合并 |
| `develop` | 开发分支，PR 目标分支 |

## ❓ 问题

有疑问？开一个 [Discussion](https://github.com/TZHR-invest/memory_recall/discussions) 或 Issue。
