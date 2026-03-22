# 更新日志

本文档记录项目的所有重要更改。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

---

## [Unreleased]

### Added - 新增功能
- 无

### Changed - 变更
- 无

### Fixed - 修复
- **BM25 中文分词问题**：修复 `_bm25_rerank` 方法使用 `query.split()` 无法正确分隔中文词组的问题
  - 使用 `jieba 分词` 替换 `query.split()`
  - 将英文关系类型转换成中文，以更好地匹配中文查询
  - 测试验证：所有测试用例通过 ✅
  - 相关文件：`apps/api/src/services/graph_recall_service.py`
  - 详细报告：`docs/bm25_chinese_tokenization_fix.md`

### Removed - 移除
- 无

---

## [0.1.0] - 2026-03-19

### Added - 新增功能
- 初始版本发布
- 基础记忆召回功能
- 图谱增强召回
- 实体提取与关系建立
- 向量搜索与 BM25 重排序

---

## 版本说明

- **[Unreleased]**: 开发中的功能
- **[0.1.0]**: 初始版本
