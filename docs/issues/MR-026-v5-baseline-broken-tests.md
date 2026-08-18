# MR-026: v5 基线坏测试（Python 3.14 环境 + 签名漂移）

> 状态: OPEN · 严重度: P2 · 发现: 2026-08-18（crystal M1 全量回归时）· 系统: v5

## 现象

crystal M1 全量回归时，v5 快循环（TESTING.md 常用命令）在**纯净基线**（stash 掉全部 M1 改动）
上即报 6 个失败，与 M1 改动零相关：

| 测试 | 失败原因 | 类别 |
|------|---------|------|
| `test_v2/test_extract_memory_whitelist.py::test_distill_type_whitelist_normalization` | `extract_memory_from_summary() got an unexpected keyword argument 'container_tag'` — 测试直调函数传 `container_tag=`，但实现签名是 `(request, current_user=Depends(...))`，测试从未适配 API 依赖注入形态 | 签名漂移（测试与实现脱节） |
| `test_v2/test_profile_worthy_write.py::TestProfileWorthyWrite`（5 个） | `RuntimeError: There is no current event loop in thread 'MainThread'` — pytest-asyncio module loop 下 `asyncio.run` 冲突 | Python 3.14 环境问题 |

## 根因分析

1. **签名漂移**：`test_extract_memory_whitelist.py` 是蒸馏白名单归一化的临时验证脚本（commit 3311a40 时代），
   直接调用 `extract_memory_from_summary(request, container_tag=...)`，而该函数早已改为 FastAPI 依赖注入形态。
   该测试**从未真正通过过**（或被 `-x` 截断从未跑全），属历史遗留坏测试。
2. **环境问题**：`test_profile_worthy_write.py`（commit 13bc89e，2026-08-18 画像净化）在 Python 3.14 +
   pytest-asyncio 1.x module loop 下 `asyncio.run()` 与既有 loop 冲突。Python 3.9 时代没问题，
   3.14 的 asyncio 行为变化导致。

## 影响

- 全量回归必须 `--deselect` 这 6 个，否则 `-x` 模式中断；
- 不影响生产（测试层问题）；画像净化功能（commit 13bc89e）本身已上线验证。

## 修复建议（未排期）

1. `test_extract_memory_whitelist.py`：改为通过 `TestClient` 调 `/extract-memory` 端点（mock LLM client），
   或直接构造 `current_user` dict 传参——需先确认该函数是否仍导出可直调。
2. `test_profile_worthy_write.py`：去掉 `asyncio.run`，改用 pytest-asyncio 原生 async 测试函数
   （与 crystal 集成测试同模式），或在模块级 loop 内跑。

## 关联

- [TESTING.md](../../docs/TESTING.md)（三层分级与环境注意点）
- MR-024（测试连接管理，同类测试基建问题）
