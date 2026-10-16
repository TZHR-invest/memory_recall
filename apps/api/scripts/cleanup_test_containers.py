#!/usr/bin/env python3
"""
测试容器残留清理脚本

背景（2026-09-22 第 4 次人工清理后固化；2026-10-16 第 5 次清理后补探针判据）：
`TESTING.md` 明确「集成测试不清理自己的测试数据」，而每次跑集成/插件测试都会**新建**容器
（`test_integration_*`、`test_perf_*`、`project-capture-test-<ts>`、`project-recall-test-<ts>`、
`project-debug<N>-<ts>`、`project-e2e-test`、`project-update-test` …）。历史上 08-14 / 08-15 /
08-17 各人工清过一次，之后又长回来 —— 所以把判据与删除动作固化成脚本。

判据（可判定命名 / 可判定数据，不含"看起来像"）：
1. 无 keyId 前缀的测试容器：`test_*`、`user_test`
2. keyId 前缀 + 测试/调试后缀：`_project-{capture-(accum|test|throttle)-<ts>|recall-test[-<ts>]|
   debug<N>[-<ts>]|debug-tag|e2e-test|update-test}`
3. 历史 bug 产物：`_project-`（空项目名，cwd=`/` 导致）、`_project-root`、拼错的 keyId
4. 仅日志残留且**零记忆/零实体/零文档**的 tag：`_project-{tmp,stock,deepseek-harness,office_64g}`
   （`tmp` 是工具验证容器；其余是插件 tag 探测留下的空壳）
5. 内容自证的跨容器测试行：`content LIKE 'MEMDECK-CROSS-CONTAINER-TEST-%'`
6. **探针残留（命名 + 数据双条件，2026-10-16 第 5 次清理后补）**：命名里 `probe` / `probes`
   / `probe<数字>` 是**独立片段**（以 `-`/`_` 或首尾分隔，如 `_project-mr-gate-probe`、
   `_project-mr-probe2`）**且该容器 0 条有效记忆**（有效 = `is_latest AND NOT is_forgotten`）。
   成因：探针动作是「写一条 → 验证 → memory_forget」，而 forget 是**软删除**（只置
   `is_forgotten=TRUE`，行/图谱/日志都留着）⇒ 容器留下 1 行已遗忘记忆，看板"有效记忆"显示 0。
   **为何必须双条件**：只看命名会误删有真实内容的调试容器（如历史 `latency-probe`）；
   只看"0 有效"会误删"整容器被遗忘"的真实容器。
   已知边界（记录在案）：真实项目若恰以 probe 命名**且**其全部记忆都被遗忘，仍会被扫到 ——
   故默认 dry-run、删除前强制备份、`PROTECTED_SUFFIXES` 保护名单照旧生效；
   另可用 `--skip-probe` 临时停用本条判据。

安全设计：
- **默认 dry-run**，必须显式 `--apply` 才删
- 删除前**强制备份**（各表受影响行 → `backups/test-containers-rollback-<日期>.json`）
- **保护名单**：有真实内容的容器一律不删（`ai-agent` / `deployment` 等机器/项目 tag 已实测含真知识）
- 单事务删除，含子表（memory_entities / memory_relations / chunk_entities / chunks）
- 删完自动复核残留 = 0
- 预览时逐条标注命中哪条判据（`[命名]` / `[探针]`）并打印有效记忆数，便于人工复核

用法:
    python scripts/cleanup_test_containers.py --dry-run     # 预览（默认）
    python scripts/cleanup_test_containers.py --apply       # 备份 + 执行
    python scripts/cleanup_test_containers.py --apply --no-backup   # 跳过备份（不推荐）
    python scripts/cleanup_test_containers.py --skip-probe  # 停用探针判据（只按命名扫）
"""

import argparse
import asyncio
import json
import os
import re
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.database import db  # noqa: E402

# 有真实内容、**必须保留**的容器后缀（防误删，随发现补充）
PROTECTED_SUFFIXES = ("project-ai-agent", "project-deployment", "_hermes")

JUNK_NAMED_PREDICATE = r"""
  tag LIKE 'test\_%' OR tag = 'user_test'
  OR tag = '085288ba-8eab-439b-b0d4-b92382e0f95d_project-'
  OR tag ~ '^085288ba-8eab-439b-b0d4-b92382e095d$'
  OR tag ~ '^085288ba-8eab-439b-b0d4-b92382e0f95d_project-(capture-(accum|test|throttle)-[0-9]+|recall-test(-[0-9]+)?|debug[0-9]*(-[0-9]+)?|debug-tag|e2e-test|update-test|tmp|root|stock|deepseek-harness|office_64g|dshte)$'
"""

# 判据 6：探针残留 = 命名里 probe 是独立片段 **且** 0 条有效记忆（docstring 第 6 条）
# 片段形态：`probe` / `probes` + 可选数字（紧跟 `probe2` 或分隔 `probe-2`），且两侧是
# 串首尾或 `-`/`_`（`mrprobe` / `reprobe-test` 这类"含 probe 子串"不算独立片段）。
# ⚠️ 正则必须与下面的 Python 侧 PROBE_NAME_RE 保持一致（一处改两处看）
PROBE_NAME_PATTERN = r"(^|[-_])probes?([0-9]+|[-_][0-9]+)?($|[-_])"
PROBE_JUNK_PREDICATE = """
  tag ~* '{pattern}'
  AND NOT EXISTS (
    SELECT 1 FROM memories m
    WHERE m.container_tag = tag
      AND m.is_latest = TRUE AND m.is_forgotten = FALSE
  )
""".format(pattern=PROBE_NAME_PATTERN)

PROBE_NAME_RE = re.compile(PROBE_NAME_PATTERN, re.IGNORECASE)

# 默认判据 = 命名判据 ∪ 探针判据（`--skip-probe` 时只用前者）
JUNK_PREDICATE = "({named})\n  OR ({probe})".format(
    named=JUNK_NAMED_PREDICATE, probe=PROBE_JUNK_PREDICATE
)

# 说明：`dshte` 是 2026-09-11 的工具验证容器（web_search/web_fetch 行为笔记），
# 经用户 2026-09-22 确认删除后并入本判据；原代码里它曾被列进 PROTECTED_SUFFIXES（已移除）。


ALL_TAGS_SQL = """
SELECT DISTINCT tag FROM (
  SELECT container_tag AS tag FROM memories
  UNION ALL SELECT container_tag FROM entities
  UNION ALL SELECT container_tag FROM documents
  UNION ALL SELECT container_tag FROM memory_profiles
  UNION ALL SELECT container_tag FROM recall_traces
  UNION ALL SELECT container_tag FROM recall_embedding_logs
) s
WHERE {pred}
"""


def _protected(tag: str) -> bool:
    return any(tag.endswith(s) for s in PROTECTED_SUFFIXES)


async def list_junk(include_probe: bool = True):
    pred = JUNK_PREDICATE if include_probe else JUNK_NAMED_PREDICATE
    rows = await db.fetch(ALL_TAGS_SQL.format(pred=pred))
    return sorted(r["tag"] for r in rows if not _protected(r["tag"]))


def matched_by(tag: str) -> str:
    """命中哪条判据（预览用）：探针判据优先标注，便于人工复核删除依据。"""
    return "探针" if PROBE_NAME_RE.search(tag) else "命名"


async def stats(tags):
    out = {}
    for t in tags:
        out[t] = {
            "memories": await db.fetchval("SELECT count(*) FROM memories WHERE container_tag=$1", t),
            "active": await db.fetchval(
                "SELECT count(*) FROM memories WHERE container_tag=$1 AND is_latest = TRUE AND is_forgotten = FALSE", t
            ),
            "entities": await db.fetchval("SELECT count(*) FROM entities WHERE container_tag=$1", t),
            "documents": await db.fetchval("SELECT count(*) FROM documents WHERE container_tag=$1", t),
            "logs": await db.fetchval("SELECT count(*) FROM recall_embedding_logs WHERE container_tag=$1", t),
        }
    return out


async def backup(tags, path):
    data = {}
    for tbl in ("memories", "entities", "documents", "memory_profiles", "recall_traces", "recall_embedding_logs"):
        rows = await db.fetch(
            f"SELECT row_to_json(t) AS r FROM {tbl} t WHERE container_tag = ANY($1::text[])", tags
        )
        data[tbl] = [json.loads(r["r"]) for r in rows]
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, ensure_ascii=False)
    try:
        # 容器内以 root 运行 ⇒ 生成的文件属 root；这里放开读权限，方便宿主查看
        os.chmod(path, 0o644)
    except OSError:
        pass
    return {k: len(v) for k, v in data.items()}


async def apply_cleanup(tags):
    """单事务删除（含子表）。

    ⚠️ asyncpg **不允许一次 execute 传多条语句**（`cannot insert multiple commands into a
    prepared statement`）——必须逐条执行，且共用同一个连接（临时表是会话级的），
    否则后续语句看不到 `junk_tags`。事务内 `ON COMMIT DROP` 保证临时表自动清理。
    """
    statements = [
        """CREATE TEMP TABLE junk_tags ON COMMIT DROP AS
           SELECT DISTINCT tag FROM (
             SELECT container_tag AS tag FROM memories
             UNION ALL SELECT container_tag FROM entities
             UNION ALL SELECT container_tag FROM documents
             UNION ALL SELECT container_tag FROM memory_profiles
             UNION ALL SELECT container_tag FROM recall_traces
             UNION ALL SELECT container_tag FROM recall_embedding_logs
           ) s WHERE tag = ANY($1::text[])""",
        "CREATE TEMP TABLE junk_mems ON COMMIT DROP AS SELECT id FROM memories WHERE container_tag IN (SELECT tag FROM junk_tags)",
        "CREATE TEMP TABLE junk_docs ON COMMIT DROP AS SELECT id FROM documents WHERE container_tag IN (SELECT tag FROM junk_tags)",
        "CREATE TEMP TABLE junk_chunks ON COMMIT DROP AS SELECT id FROM chunks WHERE document_id IN (SELECT id FROM junk_docs)",
        "DELETE FROM chunk_entities WHERE chunk_id IN (SELECT id FROM junk_chunks)",
        "DELETE FROM chunks WHERE id IN (SELECT id FROM junk_chunks)",
        "DELETE FROM memory_relations WHERE from_memory_id IN (SELECT id FROM junk_mems) OR to_memory_id IN (SELECT id FROM junk_mems)",
        "DELETE FROM memory_entities WHERE memory_id IN (SELECT id FROM junk_mems)",
        "DELETE FROM entities WHERE container_tag IN (SELECT tag FROM junk_tags)",
        "DELETE FROM entity_relations WHERE container_tag IN (SELECT tag FROM junk_tags)",
        "DELETE FROM memories WHERE id IN (SELECT id FROM junk_mems)",
        "DELETE FROM documents WHERE id IN (SELECT id FROM junk_docs)",
        "DELETE FROM memory_profiles WHERE container_tag IN (SELECT tag FROM junk_tags)",
        "DELETE FROM recall_traces WHERE container_tag IN (SELECT tag FROM junk_tags)",
        "DELETE FROM recall_embedding_logs WHERE container_tag IN (SELECT tag FROM junk_tags)",
        "DELETE FROM memories WHERE content LIKE 'MEMDECK-CROSS-CONTAINER-TEST-%'",
    ]
    async with db.transaction() as conn:
        await db.execute(statements[0], tags, conn=conn)
        for stmt in statements[1:]:
            await db.execute(stmt, conn=conn)


async def main():
    ap = argparse.ArgumentParser(description="清理测试容器残留（默认 dry-run）")
    ap.add_argument("--dry-run", action="store_true", help="预览（默认行为，显式写法）")
    ap.add_argument("--apply", action="store_true", help="真正执行删除（默认只预览）")
    ap.add_argument("--no-backup", action="store_true", help="跳过备份（不推荐）")
    ap.add_argument("--backup-dir", default="backups", help="备份目录（默认 apps/api/backups）")
    ap.add_argument("--skip-probe", action="store_true",
                    help="停用探针判据（命名含 probe 且 0 有效记忆），只按命名判据扫")
    args = ap.parse_args()
    include_probe = not args.skip_probe

    await db.connect()
    try:
        tags = await list_junk(include_probe=include_probe)
        if not tags:
            print("✅ 无测试容器残留" + ("（已停用探针判据）" if not include_probe else ""))
            return 0
        st = await stats(tags)
        total = {k: sum(v[k] for v in st.values()) for k in ("memories", "entities", "documents", "logs")}
        print(f"发现 {len(tags)} 个测试容器，合计 记忆 {total['memories']} / 实体 {total['entities']} / "
              f"文档 {total['documents']} / 日志 {total['logs']}"
              + ("　（探针判据已停用）" if not include_probe else "") + "\n")
        for t in tags:
            s = st[t]
            print(f"  [{matched_by(t)}] {t}  记忆={s['memories']:<3} 有效={s['active']:<3} "
                  f"实体={s['entities']:<3} 文档={s['documents']:<3} 日志={s['logs']}")
        print("\n判据：探针 = 命名含 probe 独立片段 且 0 条有效记忆（有效 = is_latest AND NOT is_forgotten）")

        if not args.apply:
            print("（dry-run，未删除。加 --apply 执行）")
            return 0

        if not args.no_backup:
            path = os.path.join(args.backup_dir,
                                f"test-containers-rollback-{datetime.now():%Y%m%d-%H%M%S}.json")
            counts = await backup(tags, path)
            print(f"\n已备份 → {path}  {counts}")
        await apply_cleanup(tags)
        left = await list_junk(include_probe=include_probe)
        print(f"\n删除完成，残留复核：{len(left)} 个" + (f"（异常！{left}）" if left else " ✅"))
        print("提示：跨容器测试行（MEMDECK-CROSS-CONTAINER-TEST-*）已在同一事务内清理")
        return 1 if left else 0
    finally:
        await db.disconnect()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
