#!/usr/bin/env python3
"""
M2.1 存量 claim 重建脚本（dry-run 版，2026-08-19）

用途：展示"从 evidence 重新拆条对账会产出什么"，供用户确认后再执行真重建。

模式：
    --dry-run  只打印预期：每条 evidence 会走什么路径（拆条/隔离/降级）、预计 claim 数
    --apply    真执行：清理 crystal.claim 全部行 → 对每条 evidence 跑 reconcile_evidence
               （新拆条逻辑）→ 产出原子 claim

前置：正式库已跑 init_crystal_db.py（event_key/quoted_text 列就位）+ 备份已做。

安全：
- 备份：crystal_claim/claim_evidence/lineage_edge/claim_activity 已导出 CSV（/tmp 容器内）
- --apply 前必须 --dry-run 确认
- evidence 层不动（不可再生，只重建派生层 claim）
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.database import db
from src.api.crystal.reconcile_service import (
    reconcile_evidence,
    MAX_EVIDENCE_CHARS,
    MAX_CLAIMS_PER_EVIDENCE,
    _llm_decompose_claims,
)


async def dry_run() -> None:
    """只读模拟：对每条 evidence 拆条（LLM ①），打印预期路径与 claim 数。"""
    async with db.get_connection() as conn:
        evs = await conn.fetch(
            """SELECT e.*, p.processing_state, p.current_step
               FROM crystal.evidence e
               LEFT JOIN crystal.evidence_processing p ON p.evidence_id = e.id
               ORDER BY length(e.content) DESC"""
        )
    print(f"共 {len(evs)} 条 evidence\n")

    total_claims = 0
    isolated = []
    for ev in evs:
        ev_dict = dict(ev)
        content_len = len(ev_dict["content"])
        if content_len > MAX_EVIDENCE_CHARS:
            isolated.append(ev_dict["id"])
            print(f"[隔离] {ev_dict['id']} 字数 {content_len} > {MAX_EVIDENCE_CHARS} → 不拆条，留存 workbench 待裁决")
            continue
        # 拆条（真实 LLM ①，只读不落库）
        try:
            claims = await _llm_decompose_claims(ev_dict)
            n = len(claims)
            if n > MAX_CLAIMS_PER_EVIDENCE:
                isolated.append(ev_dict["id"])
                print(f"[隔离] {ev_dict['id']} 拆出 {n} 条 > {MAX_CLAIMS_PER_EVIDENCE} → 留存 workbench 待裁决")
                continue
            total_claims += n
            preview = " | ".join(c["statement"][:40] for c in claims[:3])
            more = f" ...共 {n} 条" if n > 3 else ""
            print(f"[拆条] {ev_dict['id']} ({content_len}字, {ev_dict['source_kind']}, scope={ev_dict['scope']}) → {n} 条: {preview}{more}")
        except Exception as e:
            print(f"[失败] {ev_dict['id']} 拆条异常: {e}")

    print(f"\n预计：{total_claims} 条原子 claim + {len(isolated)} 条隔离（workbench 待裁决）")
    print(f"当前：22 条 claim（19 active + 3 superseded）→ 重建后粒度将收敛")


async def apply() -> None:
    """真重建：清空派生层 → 对每条 evidence 重新对账（拆条）。"""
    # 确认
    answer = input("确认执行存量重建？此操作清空 crystal.claim/lineage/claim_evidence/claim_activity 并重新对账（evidence 不动）。输入 YES 继续: ")
    if answer.strip() != "YES":
        print("已取消")
        return

    await db.connect()
    try:
        async with db.get_connection() as conn:
            # 清理派生层（evidence 不可再生不动）
            print("清理派生层（claim/lineage/claim_evidence/claim_activity）...")
            await conn.execute("DELETE FROM crystal.lineage_edge")
            await conn.execute("DELETE FROM crystal.claim_activity")
            await conn.execute("DELETE FROM crystal.claim_evidence")
            await conn.execute("DELETE FROM crystal.claim")
            # 重置 evidence_processing（重新对账）
            await conn.execute(
                """UPDATE crystal.evidence_processing
                   SET processing_state='pending', current_step='embedding', last_error=NULL, updated_at=NOW()"""
            )
            ev_ids = [r["id"] for r in await conn.fetch("SELECT id FROM crystal.evidence")]

        print(f"对 {len(ev_ids)} 条 evidence 重新对账（拆条）...")
        results = {"done": 0, "isolated": 0, "failed": 0}
        for ev_id in ev_ids:
            try:
                r = await reconcile_evidence(ev_id)
                results[r.get("status", "done")] = results.get(r.get("status", "done"), 0) + 1
                if r.get("status") == "done":
                    print(f"  {ev_id}: {len(r.get('created_claim_ids', []))} 条 claim")
                else:
                    print(f"  {ev_id}: {r.get('status')} ({r.get('reason', '')})")
            except Exception as e:
                results["failed"] += 1
                print(f"  {ev_id}: 异常 {e}")
        print(f"\n重建完成: {results}")
    finally:
        await db.disconnect()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="M2.1 存量 claim 重建")
    parser.add_argument("--dry-run", action="store_true", help="只打印预期（不真改）")
    parser.add_argument("--apply", action="store_true", help="真执行重建")
    args = parser.parse_args()
    if args.apply:
        asyncio.run(apply())
    else:
        asyncio.run(dry_run())
