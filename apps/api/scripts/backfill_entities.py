#!/usr/bin/env python3
"""
实体/关系回填脚本（LLM 抽取降级期间写入的记忆）

背景（2026-10-16 事故）：
opencodex 上游 `commandcode` 账号自 2026-10-04 13:36 起额度耗尽（400 insufficient credits），
此后每条新记忆的实体/关系都退回规则抽取（`relations: []` 写死为空）：
实体/天 200~685 → 11~27，entity_relations 基本归零，56% 的新记忆零实体。
模型恢复后，这些记忆的抽取结果需要按当时的原文重算一遍（原文都在库里，无损）。

判据（默认）：
- `is_latest = TRUE AND is_forgotten = FALSE`
- `created_at >= --since`（默认 2026-10-04）
- **零实体链接** 或 `metadata ? '_extraction_degraded'`（降级标记，2026-10-16 起由
  memory_store 写入）

做法：对每条记忆重跑 `LLMEntityExtractor.extract_with_relations()`（与线上同一函数、
同一 prompt），再走 `memory_store._store_entity_graph()` 落库（与线上同一条写路径），
最后写 `metadata.entities`、清 `_extraction_degraded`、记 `_extraction_backfilled_at`。

幂等：已跑过的记忆因 `_extraction_degraded` 被清且已有实体链接，默认会被跳过（不会重复处理）；
`--force` 可强制重算。默认 dry-run，`--apply` 才写库。

用法（必须在 api 容器内跑，那里才有 DB/VOLC/opencodex 环境变量与依赖）：
    docker exec -i memory_recall-api-1 python scripts/backfill_entities.py --dry-run
    docker exec -i memory_recall-api-1 python scripts/backfill_entities.py --apply
    docker exec -i memory_recall-api-1 python scripts/backfill_entities.py --apply --since 2026-10-04 --limit 20
"""

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.database import db  # noqa: E402
from src.services.core.memory_store import memory_store  # noqa: E402

SELECT_SQL = """
SELECT m.id, m.container_tag, m.content, m.created_at, m.metadata,
       (SELECT count(*) FROM memory_entities me WHERE me.memory_id = m.id) AS entity_links
FROM memories m
WHERE m.is_latest = TRUE
  AND m.is_forgotten = FALSE
  AND m.created_at >= $1
  AND ($2::text IS NULL OR m.container_tag = $2)
  AND (m.metadata ? '_extraction_degraded'
       OR NOT EXISTS (SELECT 1 FROM memory_entities me WHERE me.memory_id = m.id))
ORDER BY m.created_at
LIMIT $3
"""


async def run(args):
    since = datetime.fromisoformat(args.since).replace(tzinfo=timezone.utc)
    await db.connect()
    try:
        rows = await db.fetch(SELECT_SQL, since, args.container, args.limit)
        if not rows:
            print("✅ 没有需要回填的记忆")
            return 0

        print(f"候选 {len(rows)} 条（since={args.since}，container={args.container or '全部'}）")
        by_day = {}
        for r in rows:
            by_day.setdefault(str(r["created_at"])[:10], 0)
            by_day[str(r["created_at"])[:10]] += 1
        print("按日期分布：" + "  ".join(f"{d}:{n}" for d, n in sorted(by_day.items())))

        if args.dry_run:
            for r in rows[:10]:
                print(f"  - {r['id']} {str(r['created_at'])[:16]} links={r['entity_links']} "
                      f"{r['content'][:60]!r}")
            if len(rows) > 10:
                print(f"  ...（其余 {len(rows) - 10} 条略）")
            print("\n（dry-run，未写库。加 --apply 执行）")
            return 0

        extractor = memory_store._get_llm_extractor()
        ok = skipped = failed = 0
        ent_total = rel_total = 0
        for i, r in enumerate(rows, 1):
            # asyncpg 默认把 jsonb 返回成字符串（应用侧 Memory 模型也是这么解的）
            raw_meta = r["metadata"]
            meta = json.loads(raw_meta) if isinstance(raw_meta, str) else dict(raw_meta or {})
            if r["entity_links"] and not meta.get("_extraction_degraded") and not args.force:
                skipped += 1
                continue
            try:
                extraction = await extractor.extract_with_relations(r["content"])
            except Exception as e:  # noqa: BLE001
                failed += 1
                print(f"  ✗ {r['id']} 抽取异常：{type(e).__name__}: {e}")
                continue

            degraded = extraction.get("degraded")
            entities = extraction.get("entities") or []
            relations = extraction.get("relations") or []
            if degraded:
                failed += 1
                print(f"  ✗ {r['id']} 仍处于降级（{degraded}）——跳过，改天重试")
                continue

            try:
                if entities or relations:
                    await memory_store._store_entity_graph(
                        r["id"], entities, relations, r["container_tag"]
                    )
                entities_dict = {}
                for e in entities:
                    entities_dict.setdefault(e.get("type", "unknown"), []).append(e.get("name"))
                meta["entities"] = entities_dict
                meta.pop("_extraction_degraded", None)
                meta["_extraction_backfilled_at"] = datetime.now(timezone.utc).isoformat()
                await memory_store.update_metadata(r["id"], meta)
            except Exception as e:  # noqa: BLE001
                failed += 1
                print(f"  ✗ {r['id']} 落库失败：{type(e).__name__}: {e}")
                continue

            ok += 1
            ent_total += len(entities)
            rel_total += len(relations)
            if i % 10 == 0 or i == len(rows):
                print(f"  … 进度 {i}/{len(rows)}（成功 {ok} / 跳过 {skipped} / 失败 {failed}；"
                      f"实体 {ent_total}，关系 {rel_total}）")
            if args.sleep:
                await asyncio.sleep(args.sleep)

        print(f"\n回填完成：成功 {ok} 条（实体 {ent_total}，关系 {rel_total}）、"
              f"跳过 {skipped}、失败 {failed}")
        return 0 if failed == 0 else 1
    finally:
        await db.disconnect()


def main():
    ap = argparse.ArgumentParser(description="回填降级期间记忆的实体/关系（默认 dry-run）")
    ap.add_argument("--apply", action="store_true", help="真正写库（默认只预览）")
    ap.add_argument("--dry-run", action="store_true", help="预览（默认行为，显式写法）")
    ap.add_argument("--since", default="2026-10-04", help="起始日期（默认 2026-10-04）")
    ap.add_argument("--container", help="只处理某个容器")
    ap.add_argument("--limit", type=int, default=1000, help="最多处理多少条（默认 1000）")
    ap.add_argument("--force", action="store_true", help="已有实体也重算")
    ap.add_argument("--sleep", type=float, default=0.0, help="每条之间 sleep 秒数（限速）")
    args = ap.parse_args()
    return asyncio.run(run(args))


if __name__ == "__main__":
    sys.exit(main())
