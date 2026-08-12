"""
召回回归集脚本（Recall Regression Suite）

对固定 query 集执行真实召回，记录注入量/来源分布/耗时指标，
用于参数调整前后的回归对比（防止"优化"引入召回退化）。

用法（从 apps/api/ 目录运行）：
    venv/bin/python scripts/recall_regression.py --save-baseline   # 建立/更新 baseline
    venv/bin/python scripts/recall_regression.py                    # 运行并对比 baseline
    venv/bin/python scripts/recall_regression.py --query "自定义"   # 单条 query 快速验证
    venv/bin/python scripts/recall_regression.py --user-tag <keyId> --project-tag <tag>  # 指定容器

指标：
    - profile/memory/chunk 注入条数（cap 后，与实际 context 一致）
    - 总耗时
    - 每条 query 的注入构成，与 baseline 对比差异

说明：
    - user/project tag 默认从 ~/.config/opencode/memory-recall.jsonc 读取（keyId）
    - 每次运行自动清理本次产生的 trace 记录（避免污染 trace 分析数据）

退出码：0=通过（无退化），1=有退化（注入量显著下降或异常）。
"""

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import settings
from src.database import db
from src.services.core.context_inject_service import context_inject_service

# 固定 query 集（来自真实 trace 的高频 query + 覆盖不同类型场景）
DEFAULT_QUERIES = [
    "本地的memory recall插件是怎么安装的",
    "项目架构和部署方式",
    "最近的热点研究",
    "用户的项目偏好",
    "帮我更新memory recall插件",
    "运营回顾 OKR 修复",
    "补跑 run_daily_scan 漏跑交易日 脚本运行",
    "之前不是会报错吗",
    "Memory Recall 部署运维要点",
    "测试查询",
]

# 子代理场景（长英文 prompt 模拟，验证降级逻辑）
SUBAGENT_QUERIES = [
    "[CONTEXT] I'm investigating the Memory Recall project trace recording system to analyze optimization opportunities for recall quality improvement in the context injection pipeline",
]

BASELINE_FILE = Path(__file__).parent / "recall_baseline.json"

DEFAULT_USER_TAG = "085288ba-8eab-439b-b0d4-b92382e0f95d"
DEFAULT_PROJECT_TAG = "085288ba-8eab-439b-b0d4-b92382e0f95d_project-memory_recall"


def load_tags(args) -> tuple:
    """读取 user/project tag：优先 --user-tag/--project-tag，其次用户 jsonc，最后默认值。"""
    user_tag = args.user_tag
    project_tag = args.project_tag
    if not user_tag or not project_tag:
        jsonc_path = Path.home() / ".config/opencode/memory-recall.jsonc"
        if jsonc_path.exists():
            try:
                import json

                raw = jsonc_path.read_text()
                # 剥离 // 行注释（jsonc 兼容）
                lines = [l for l in raw.splitlines() if not l.strip().startswith("//")]
                cfg = json.loads("\n".join(lines))
                user_tag = user_tag or cfg.get("keyId") or DEFAULT_USER_TAG
                project_tag = project_tag or (
                    f"{cfg.get('keyId') or DEFAULT_USER_TAG}_project-memory_recall"
                )
            except Exception:
                pass
    return user_tag or DEFAULT_USER_TAG, project_tag or DEFAULT_PROJECT_TAG


async def run_query(query: str, config: dict, user_tag: str, project_tag: str) -> dict:
    """执行一次真实召回，返回指标。"""
    result = await context_inject_service.inject_with_tags(
        user_tag=user_tag,
        project_tag=project_tag,
        query=query,
        config={
            "inject_profile": True,
            "max_profile_items": 5,
            "max_static_profile_items": 20,
            "max_memories": 5,
            "max_chunks": 3,
            "enable_memory_graph": True,
            "enable_entity_graph": True,
            "enable_semantic_dedup": True,
            "language": "auto",
            **config,
        },
        include_trace=True,
    )

    stats = result.get("stats", {})
    trace = result.get("trace", {})
    return {
        "query": query,
        "profile": stats.get("profile_count", 0),
        "project_memory": stats.get("project_memories_count", 0),
        "user_memory": stats.get("user_memories_count", 0),
        "chunk": stats.get("chunks_count", 0),
        "total": stats.get("capped_count", 0),
        "elapsed_ms": round(trace.get("total_ms", 0), 1),
        "error": trace.get("error"),
    }


async def run_all(queries: list, user_tag: str, project_tag: str) -> list:
    results = []
    for q in queries:
        try:
            r = await run_query(q, {}, user_tag, project_tag)
        except Exception as e:
            r = {"query": q, "error": str(e), "profile": 0, "project_memory": 0,
                 "user_memory": 0, "chunk": 0, "total": 0, "elapsed_ms": 0}
        results.append(r)
        status = "ERROR" if r.get("error") else f"total={r['total']}"
        print(f"  [{status:>20}] {q[:50]}")
    return results


async def cleanup_traces(queries: list, start_time: datetime) -> None:
    """清理本次回归集产生的 trace 记录（按 query + 运行时间窗口匹配）。

    回归集每次运行会通过 include_trace=True 强制落库 10+ 条 trace，
    若不清理会污染 trace 分析数据（高频 query 统计/质量分布被测试数据扭曲）。
    仅删除 start_time 之后且 query 匹配的记录，避免误删历史真实 trace。
    """
    try:
        deleted = await db.execute(
            """
            DELETE FROM recall_traces
            WHERE created_at >= $1
              AND query = ANY($2)
            """,
            start_time,
            queries,
        )
        if deleted:
            print(f"  已清理本次回归产生的 trace 记录: {deleted}")
    except Exception as e:
        print(f"  ⚠️ trace 清理失败（不影响回归结果）: {e}")


def summarize(results: list) -> dict:
    totals = {"profile": 0, "project_memory": 0, "user_memory": 0, "chunk": 0}
    for r in results:
        for k in totals:
            totals[k] += r.get(k, 0)
    total_items = sum(totals.values())
    return {
        "queries": len(results),
        "totals": totals,
        "avg_total_per_query": round(total_items / len(results), 1) if results else 0,
        "errors": [r for r in results if r.get("error")],
    }


def compare(baseline: dict, current: dict) -> list:
    """对比 baseline 与当前，返回退化项列表。"""
    issues = []
    bt = baseline.get("totals", {})
    ct = current.get("totals", {})
    for k in ("profile", "project_memory", "user_memory", "chunk"):
        b, c = bt.get(k, 0), ct.get(k, 0)
        if b > 0 and c < b * 0.5:
            issues.append(
                f"{k} 注入量下降 {b}→{c}（超过 50%），疑似召回退化"
            )
    if current.get("errors"):
        issues.append(f"{len(current['errors'])} 条 query 执行出错")
    return issues


async def main():
    parser = argparse.ArgumentParser(description="召回回归集")
    parser.add_argument("--save-baseline", action="store_true",
                        help="运行并保存为 baseline（不对比）")
    parser.add_argument("--query", help="仅运行单条自定义 query")
    parser.add_argument("--include-subagent", action="store_true",
                        help="包含子代理长 prompt 场景")
    parser.add_argument("--user-tag", help="用户容器 tag（默认从 ~/.config/opencode/memory-recall.jsonc 读取）")
    parser.add_argument("--project-tag", help="项目容器 tag")
    args = parser.parse_args()

    user_tag, project_tag = load_tags(args)

    queries = [args.query] if args.query else list(DEFAULT_QUERIES)
    if args.include_subagent:
        queries += SUBAGENT_QUERIES

    start_time = datetime.now(timezone.utc)
    print(f"运行 {len(queries)} 条 query 回归（user_tag={user_tag[:12]}...）...")
    results = await run_all(queries, user_tag, project_tag)
    current = summarize(results)

    print(f"\n=== 汇总 ===")
    print(f"  query 数: {current['queries']}, 平均注入: {current['avg_total_per_query']} 条/query")
    print(f"  来源分布: profile={current['totals']['profile']} "
          f"projectMemory={current['totals']['project_memory']} "
          f"userMemory={current['totals']['user_memory']} chunk={current['totals']['chunk']}")
    if current["errors"]:
        print(f"  ⚠️ {len(current['errors'])} 条出错: {[e['query'][:30] for e in current['errors']]}")

    await cleanup_traces(queries, start_time)

    if args.save_baseline:
        BASELINE_FILE.write_text(json.dumps(current, ensure_ascii=False, indent=2))
        print(f"\n✅ baseline 已保存: {BASELINE_FILE}")
        return 0

    if args.query:
        print(f"\n单条 query 模式：仅展示指标，跳过 baseline 对比（用全量模式做回归）")
        return 0

    if BASELINE_FILE.exists():
        baseline = json.loads(BASELINE_FILE.read_text())
        issues = compare(baseline, current)
        if issues:
            print(f"\n❌ 对比 baseline 发现 {len(issues)} 个问题:")
            for i in issues:
                print(f"  - {i}")
            return 1
        print(f"\n✅ 与 baseline 对比无退化（baseline: {baseline['avg_total_per_query']} 条/query）")
    else:
        print(f"\n⏭️ 无 baseline，跳过对比（先用 --save-baseline 建立）")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
