"""
trace-id 日志基建（跨模块共用）

背景（docs/notes/2026-08-19-llm-trace-id-logging-plan.md）：
一次 evidence 对账 = evidence 落库 → embedding → 拆条（LLM ①）→ 候选检索 →
碰撞判定（LLM ②）→ 批量写，是 6+ 步调用链；过去日志是散点，排查只能靠时间戳猜关联。
本模块提供轻量 trace-id：ContextVar 在异步调用链内自动传播，
logging.Filter 把 trace_id 追加到每条日志 record，LLM client 与业务日志自动串联。

设计要点（计划 §3）：
- contextvars.ContextVar（asyncio 原生支持 Task 间自动传播，无需手动传参）
- logging.Filter 挂在 root logger（main.py 启动时挂载），只加前缀不改语义
- 入口生成 + 清理：reconcile_evidence（每条 evidence 一个 trace）
- 并发安全：ContextVar 按 Task 隔离，并发对账不串
"""
import contextvars
import logging
import uuid
from typing import Optional

# 进程内贯穿异步调用链的 trace_id（None = 无 trace 上下文）
trace_id_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "trace_id", default=None
)


def generate_trace_id(prefix: str = "ev") -> str:
    """生成 trace_id：`ev_` + 短 uuid（prefix 默认对账链路；其他业务可传自己前缀）"""
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def set_trace_id(trace_id: Optional[str]) -> contextvars.Token:
    """写入当前异步上下文的 trace_id，返回 Token（供 reset 恢复旧值）"""
    return trace_id_var.set(trace_id)


def reset_trace_id(token: contextvars.Token) -> None:
    """恢复 trace_id 到设置前的值（配合 set_trace_id 成对使用）"""
    trace_id_var.reset(token)


def get_trace_id() -> Optional[str]:
    """读取当前上下文的 trace_id（None = 不在 trace 内）"""
    return trace_id_var.get()


class TraceIdFilter(logging.Filter):
    """logging.Filter：给每条 log record 追加 `[trace_id=xxx]` 前缀。

    挂在 root logger（或任意 logger）上，该 logger 及其子 logger 的所有
    record 自动带前缀（record 无 trace_id 时输出原样，零影响）。
    """

    def filter(self, record: logging.LogRecord) -> bool:
        trace_id = get_trace_id()
        if trace_id:
            # 防重复挂载/重复前缀（同一 record 可能过多个带本 Filter 的 handler）
            if getattr(record, "trace_id", None) != trace_id:
                record.trace_id = trace_id
            if not record.getMessage().startswith(f"[trace_id={trace_id}]"):
                record.msg = f"[trace_id={trace_id}] {record.msg}"
        return True
