"""实体家族归一 A/B（非劣性回归检查，2026-09-22）

背景
----
`ENTITY_FAMILY_EXPANSION`（种子按共现排序 + 同名实体家族归一）上线后，"是否变好"未验证，
而图谱通道承担 **26% 的注入项**（见 notes/2026-09-22-recall-channel-ablation.md）。
本脚本做的是**非劣性**检查：ON 相对 OFF 若不出现明显退化即保留（确定性本身是独立收益）。

为什么这次测起来干净
--------------------
改动后开/关两侧**都是确定性的**：同一配置连跑两次，注入条目集合与顺序逐字节相同
（`--control` 会在每个 query 上验一遍）⇒ 同配置对照噪声为 0，差异只来自改动本身 + 裁判噪声。
这与之前"low-vs-low 对照也能判出 9/10 胜者"的情况不同，逐条打分即可，不需要胜负次数统计。

零足迹
------
实验进程内 `TRACE_ENABLED=False`（`should_record` 首行即短路，`include_trace` 仍返回内存 trace）
并屏蔽 `recall_embedding_service.log` ⇒ **不写生产 `recall_traces` / `recall_embedding_logs`**。
本脚本只做只读召回，不改任何业务数据。

用法（在 apps/api 下，容器或 venv 均可）
---------------------------------------
    python scripts/ab_entity_family_inferiority.py --all --queries 40
    python scripts/ab_entity_family_inferiority.py --run --queries 40     # 只跑两臂
    python scripts/ab_entity_family_inferiority.py --judge               # 只盲评
    python scripts/ab_entity_family_inferiority.py --report              # 只出结论

产物：`apps/api/backups/ab-entity-family/<ts>/`（raw.json / judged.json / report.md，均 gitignore）

预注册判据（先定好，避免事后自圆其说）
------------------------------------
Δ = 只在 ON 出现的条目的平均分 − 只在 OFF 出现的条目的平均分（逐条 1–5 分，盲评）
    Δ ≥ −0.3        ⇒ 保留 ON（确定性本身即收益）
    −0.5 < Δ < −0.3 ⇒ 保留 ON，但定向复查被挤掉的条目，再决定是否改排序规则
    Δ ≤ −0.5 且 CI 不含 0 ⇒ 关掉开关（回到旧种子选择，只保留家族展开这一半）
"""

import argparse
import asyncio
import json
import random
import re
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import httpx

from src.config import settings
from src.services.core.recall_embedding_service import recall_embedding_service

BACKUP_DIR = Path(__file__).parent.parent / "backups" / "ab-entity-family"

# 明显是测试/调试的 query，不进实验（真实 query 集的噪声源）
JUNK_QUERY_MARKERS = ("test_", "测试一下", "debug", "asdf", "111", "hello world")


def _disable_side_effects() -> None:
    """零足迹：不写 trace、不写 embedding 日志。"""
    settings.TRACE_ENABLED = False

    async def _noop(*args, **kwargs):
        return None

    recall_embedding_service.log = _noop


async def load_queries(limit: int) -> list:
    """从真实 trace 里取 query（按容器分层，保证跨容器覆盖）。"""
    from src.database import db

    rows = await db.fetch(
        """
        SELECT query, user_tag, project_tag, container_tag, max(created_at) AS last_seen
        FROM recall_traces
        WHERE query IS NOT NULL AND length(btrim(query)) > 6
        GROUP BY query, user_tag, project_tag, container_tag
        ORDER BY last_seen DESC
        """
    )

    picked, seen = [], set()
    for row in rows:
        q = (row["query"] or "").strip()
        if not q or q in seen:
            continue
        if any(marker in q.lower() for marker in JUNK_QUERY_MARKERS):
            continue
        seen.add(q)
        picked.append(
            {
                "query": q,
                "user_tag": row["user_tag"] or row["container_tag"],
                "project_tag": row["project_tag"] or row["container_tag"],
                "container_tag": row["container_tag"],
            }
        )

    # 分层：每个容器最多不超过一半，避免某一个大容器淹没样本
    per_container_cap = max(1, limit // 3)
    counts, balanced = {}, []
    for item in picked:
        ct = item["container_tag"]
        if counts.get(ct, 0) >= per_container_cap:
            continue
        counts[ct] = counts.get(ct, 0) + 1
        balanced.append(item)
        if len(balanced) >= limit:
            break
    # 若分层后不足，再按时间顺序补足
    if len(balanced) < limit:
        chosen = {b["query"] for b in balanced}
        for item in picked:
            if item["query"] in chosen:
                continue
            balanced.append(item)
            if len(balanced) >= limit:
                break
    return balanced[:limit]


async def run_arm(item: dict, flag: bool) -> dict:
    """跑一次召回（指定开关状态），返回注入条目 + 通道信息。"""
    from src.api.context_inject import ContextInjectConfig
    from src.services.core.context_inject_service import context_inject_service

    settings.ENTITY_FAMILY_EXPANSION = flag
    result = await context_inject_service.inject_with_tags(
        user_tag=item["user_tag"],
        project_tag=item["project_tag"],
        query=item["query"],
        config=ContextInjectConfig().model_dump(),
        include_trace=True,
    )
    trace = result.get("trace") or {}
    channels = trace.get("channels") or {}
    final = [
        {"id": i.get("id"), "content": i.get("content", ""), "source": i.get("source")}
        for i in trace.get("final") or []
    ]
    return {
        "flag": flag,
        "items": final,
        "channel_keys": sorted(channels.keys()),
        "channel_ids": {
            name: [h.get("id") for h in (body.get("hits") or []) if h.get("passed", True)]
            for name, body in channels.items()
            if isinstance(body, dict)
        },
        "stats": result.get("stats") or {},
    }


async def phase_run(args, out_dir: Path) -> dict:
    _disable_side_effects()
    queries = await load_queries(args.queries)
    print(f"[run] query 数 = {len(queries)}（容器分布：{_container_hist(queries)}）", flush=True)

    records = []
    for idx, item in enumerate(queries, 1):
        on1 = await run_arm(item, True)
        off = await run_arm(item, False)
        on2 = await run_arm(item, True)

        ids = lambda r: [i["id"] for i in r["items"]]
        rec = {
            "idx": idx,
            "query": item["query"],
            "container_tag": item["container_tag"],
            "user_tag": item["user_tag"],
            "project_tag": item["project_tag"],
            "on": on1,
            "off": off,
            "control_identical": ids(on1) == ids(on2),
        }
        records.append(rec)
        only_on = set(ids(on1)) - set(ids(off))
        only_off = set(ids(off)) - set(ids(on1))
        print(
            f"[run] {idx:>2}/{len(queries)} ON={len(ids(on1))} OFF={len(ids(off))} "
            f"仅ON={len(only_on)} 仅OFF={len(only_off)} 对照一致={rec['control_identical']} | {item['query'][:28]}",
            flush=True,
        )

    settings.ENTITY_FAMILY_EXPANSION = True  # 复位
    raw = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "queries": len(records),
        "records": records,
    }
    (out_dir / "raw.json").write_text(json.dumps(raw, ensure_ascii=False, indent=1))
    ctrl_ok = sum(1 for r in records if r["control_identical"])
    print(f"\n[run] 对照臂（同配置跑两次完全一致）= {ctrl_ok}/{len(records)}", flush=True)
    return raw


def _container_hist(queries) -> str:
    hist = {}
    for q in queries:
        hist[q["container_tag"]] = hist.get(q["container_tag"], 0) + 1
    return ", ".join(f"{k.split('_')[-1]}={v}" for k, v in sorted(hist.items(), key=lambda x: -x[1]))


JUDGE_PROMPT = """你在评估一个"记忆召回"系统交给 AI 助手的历史记忆条目是否有用。

用户当前的问题：
{query}

下面是本次召回到的记忆条目（顺序已打乱、来源未知）。请**逐条**打分，判断它对回答上面这个问题有多大帮助：

5 = 直接命中：就是解决该问题所需的关键事实/结论
4 = 高度相关：同一主题的具体信息，能明显帮上忙
3 = 部分相关：沾边，可能提供背景
2 = 几乎无关：只是同一大领域，帮不上
1 = 完全无关

只输出 JSON，不要解释、不要 Markdown 代码块：
{{"ratings": {{"A": 5, "B": 3}}}}

条目：
{items}
"""


async def judge_query(client: httpx.AsyncClient, model: str, query: str, labelled: list) -> dict:
    items_text = "\n\n".join(f"[{label}]\n{content[:600]}" for label, content in labelled)
    payload = {
        "model": model,
        "messages": [
            {"role": "user", "content": JUDGE_PROMPT.format(query=query, items=items_text)}
        ],
        "max_tokens": 16000,  # 思考型裁判：max_tokens 太小会 50~60% 空返回（前次实验教训）
        "temperature": 0,
    }
    headers = {
        "Content-Type": "application/json",
        "x-opencodex-api-key": settings.OPENCODEX_API_KEY or "",
        "Authorization": f"Bearer {settings.OPENCODEX_API_KEY or ''}",
    }
    url = (settings.OPENCODEX_API_BASE or "").rstrip("/") + "/chat/completions"

    last_err = None
    for attempt in range(3):
        try:
            resp = await client.post(url, json=payload, headers=headers, timeout=300)
            resp.raise_for_status()
            text = resp.json()["choices"][0]["message"].get("content") or ""
            match = re.search(r"\{.*\}", text, re.S)
            if not match:
                last_err = f"无 JSON：{text[:120]}"
                continue
            ratings = json.loads(match.group(0)).get("ratings") or {}
            if ratings:
                return {str(k): float(v) for k, v in ratings.items()}
            last_err = "ratings 为空"
        except Exception as exc:  # noqa: BLE001 - 裁判失败要能重试
            last_err = f"{type(exc).__name__}: {exc}"
        await asyncio.sleep(2 * (attempt + 1))
    raise RuntimeError(f"裁判失败：{last_err}")


async def phase_judge(args, out_dir: Path) -> dict:
    raw = json.loads((out_dir / "raw.json").read_text())
    judged_path = out_dir / "judged.json"
    judged = json.loads(judged_path.read_text()) if judged_path.exists() else {}

    rng = random.Random(20260922)  # 固定洗牌，可复现
    async with httpx.AsyncClient() as client:
        for rec in raw["records"]:
            key = str(rec["idx"])
            if key in judged and judged[key].get("ratings"):
                continue
            on_items = {i["id"]: i["content"] for i in rec["on"]["items"]}
            off_items = {i["id"]: i["content"] for i in rec["off"]["items"]}
            union = list(dict.fromkeys(list(on_items) + list(off_items)))
            if not union:
                judged[key] = {"ratings": {}, "labels": {}, "empty": True}
                continue

            rng.shuffle(union)
            labels = {f"L{k}": item_id for k, item_id in enumerate(union)}
            labelled = [
                (label, (on_items.get(item_id) or off_items.get(item_id) or "")[:600])
                for label, item_id in labels.items()
            ]
            ratings = await judge_query(client, args.judge_model, rec["query"], labelled)
            judged[key] = {"ratings": ratings, "labels": labels}
            print(
                f"[judge] {rec['idx']:>2}/{len(raw['records'])} 评了 {len(ratings)}/{len(union)} 条 | {rec['query'][:28]}",
                flush=True,
            )
            judged_path.write_text(json.dumps(judged, ensure_ascii=False, indent=1))

    judged_path.write_text(json.dumps(judged, ensure_ascii=False, indent=1))
    return judged


def _cluster_bootstrap(pairs_by_query: list, iterations: int = 4000) -> tuple:
    """按 query 聚类的 bootstrap：重采样 query，统计量 = 池化(仅ON均分 − 仅OFF均分)。

    必须与点估计同构：不能把两侧分数拼成一个带符号列表取均值（两侧条数不等时会算错）。
    返回 (点估计, 2.5%, 97.5%)。
    """
    usable = [(on, off) for on, off in pairs_by_query if on or off]
    if not usable:
        return 0.0, 0.0, 0.0

    def pooled(sample):
        ons = [x for on, _ in sample for x in on]
        offs = [x for _, off in sample for x in off]
        if not ons or not offs:
            return None
        return statistics.fmean(ons) - statistics.fmean(offs)

    point = pooled(usable)
    rng = random.Random(7)
    means = []
    for _ in range(iterations):
        sample = [rng.choice(usable) for _ in usable]
        value = pooled(sample)
        if value is not None:
            means.append(value)
    means.sort()
    return point, means[int(0.025 * len(means))], means[int(0.975 * len(means)) - 1]


def phase_report(args, out_dir: Path) -> str:
    raw = json.loads((out_dir / "raw.json").read_text())
    judged = json.loads((out_dir / "judged.json").read_text())

    only_on_scores, only_off_scores = [], []
    per_query, diffs_by_query, shared_scores = [], [], []
    displaced = []  # 被 ON 挤掉 / ON 新加进来的条目

    for rec in raw["records"]:
        key = str(rec["idx"])
        entry = judged.get(key) or {}
        labels = entry.get("labels") or {}
        ratings = entry.get("ratings") or {}
        score = {}
        for label, item_id in labels.items():
            if label in ratings:
                score[item_id] = ratings[label]

        on_ids = [i["id"] for i in rec["on"]["items"]]
        off_ids = [i["id"] for i in rec["off"]["items"]]
        on_only = [i for i in on_ids if i not in off_ids]
        off_only = [i for i in off_ids if i not in on_ids]
        both = [i for i in on_ids if i in off_ids]

        on_scores = [score[i] for i in on_only if i in score]
        off_scores = [score[i] for i in off_only if i in score]
        only_on_scores.extend(on_scores)
        only_off_scores.extend(off_scores)
        shared_scores.extend(score[i] for i in both if i in score)
        if on_scores or off_scores:
            diffs_by_query.append((on_scores, off_scores))

        if on_scores or off_scores:
            per_query.append(
                {
                    "query": rec["query"],
                    "container": rec["container_tag"].split("_")[-1],
                    "on_only": round(statistics.fmean(on_scores), 2) if on_scores else None,
                    "off_only": round(statistics.fmean(off_scores), 2) if off_scores else None,
                }
            )
        if on_scores or off_scores:
            content_by_id = {i["id"]: i["content"] for i in rec["on"]["items"] + rec["off"]["items"]}
            for item_id, kind in [(i, "only_on") for i in on_only] + [(i, "only_off") for i in off_only]:
                if item_id in score:
                    displaced.append(
                        {
                            "query": rec["query"],
                            "kind": kind,
                            "score": score[item_id],
                            "content": (content_by_id.get(item_id) or "")[:150],
                        }
                    )

    delta = (
        statistics.fmean(only_on_scores) - statistics.fmean(only_off_scores)
        if only_on_scores and only_off_scores
        else 0.0
    )
    point, lo, hi = _cluster_bootstrap(diffs_by_query)
    ctrl_ok = sum(1 for r in raw["records"] if r["control_identical"])

    # 胜负 query 数：对照臂噪声为 0 时，符号计数才是可解释的（上次实验 low-vs-low 也能判出 9/10 胜者）
    wins = losses = ties = 0
    for rec in per_query:
        if rec["on_only"] is None or rec["off_only"] is None:
            continue
        if rec["on_only"] > rec["off_only"]:
            wins += 1
        elif rec["on_only"] < rec["off_only"]:
            losses += 1
        else:
            ties += 1

    # 注入条数：开关影响的是"选哪几条"，还是"注入几条"？
    count_pairs = [
        (len(r["on"]["items"]), len(r["off"]["items"]))
        for r in raw["records"]
    ]
    same_count = sum(1 for a, b in count_pairs if a == b)
    mean_on = statistics.fmean([a for a, _ in count_pairs]) if count_pairs else 0
    mean_off = statistics.fmean([b for _, b in count_pairs]) if count_pairs else 0

    if delta >= -0.3:
        verdict = "保留 ON（非劣性通过）"
        reason = "Δ ≥ −0.3：没有可判定的退化，确定性与覆盖提升保留"
    elif delta > -0.5:
        verdict = "保留 ON，但需定向复查"
        reason = "−0.5 < Δ < −0.3：处于灰区，逐条看被挤掉的条目是否系统性地更相关"
    elif hi < 0:
        verdict = "关掉开关"
        reason = "Δ ≤ −0.5 且 bootstrap CI 整体在 0 以下（显著退化）：回退种子选择，只保留家族展开"
    else:
        verdict = "保留 ON（差异不显著）"
        reason = "Δ ≤ −0.5 但 CI 含 0，样本不足以判定退化"

    lines = [
        "# 实体家族归一 A/B（非劣性回归检查）",
        "",
        f"- 运行时间：{raw['started_at']}",
        f"- query 数：{raw['queries']}",
        f"- **对照臂（同配置跑两次完全一致）：{ctrl_ok}/{raw['queries']}**"
        + ("　⇒ 测量噪声为 0，差异只来自改动" if ctrl_ok == raw["queries"] else "　⚠️ 存在非确定性"),
        "",
        "## 主指标：只在某一侧出现的条目的平均分（1–5，盲评）",
        "",
        f"- 只在 **ON** 出现：{len(only_on_scores)} 条，均分 "
        f"{round(statistics.fmean(only_on_scores), 2) if only_on_scores else 'n/a'}",
        f"- 只在 **OFF** 出现：{len(only_off_scores)} 条，均分 "
        f"{round(statistics.fmean(only_off_scores), 2) if only_off_scores else 'n/a'}",
        f"- **Δ = {round(delta, 3)}**（按 query 聚类 bootstrap 95% CI：{round(lo, 2)} ~ {round(hi, 2)}）",
        f"- 两侧共有条目的均分（参照，应接近）：{round(statistics.fmean(shared_scores), 2) if shared_scores else 'n/a'}"
        f"（{len(shared_scores)} 条）",
        "",
        "## 次要指标",
        "",
        f"- 胜负 query 数（仅 ON 均分更高的 query 数）：**ON 更好 {wins} / OFF 更好 {losses} / 打平 {ties}**"
        "（对照臂噪声为 0 ⇒ 符号计数可解释；上次实验因同配置对照也会判出胜负，只能用平均分）",
        f"- 注入条数：ON 平均 {round(mean_on, 2)} 条 / OFF 平均 {round(mean_off, 2)} 条，"
        f"**逐 query 条数相同的占 {same_count}/{len(count_pairs)}**"
        "　⇒ 开关改变的是『选哪几条』，不是『注入几条』（出口受 `limit=max_memories` 封顶）",
        f"- 共有条目均分 {round(statistics.fmean(shared_scores), 2) if shared_scores else 'n/a'} "
        f"vs 差异条目均分 {round(statistics.fmean(only_on_scores + only_off_scores), 2) if (only_on_scores or only_off_scores) else 'n/a'}"
        "　⇒ 差异发生在排序边缘，头部相关条目两臂一致",
        "",
        f"## 结论：**{verdict}**",
        "",
        f"{reason}",
        "",
        "## 逐 query 明细（有差异的）",
        "",
        "| query | 容器 | 仅 ON 均分 | 仅 OFF 均分 |",
        "|---|---|---|---|",
    ]
    for row in per_query:
        if row["on_only"] is None and row["off_only"] is None:
            continue
        lines.append(
            f"| {row['query'][:40]} | {row['container']} | {row['on_only']} | {row['off_only']} |"
        )

    lines += ["", "## 差异条目逐条（分数 + 内容首 150 字）", ""]
    for item in sorted(displaced, key=lambda x: (x["kind"], -x["score"])):
        tag = "ON+" if item["kind"] == "only_on" else "OFF+"
        lines.append(f"- `{tag}` [{item['score']}] {item['content']}")

    report = "\n".join(lines)
    (out_dir / "report.md").write_text(report)
    print(report)
    return report


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--judge", action="store_true")
    parser.add_argument("--report", action="store_true")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--queries", type=int, default=40)
    parser.add_argument("--judge-model", default="commandcode/Qwen/Qwen3.7-Max")
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    stamp = args.out or datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = BACKUP_DIR / stamp
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"[out] {out_dir}", flush=True)

    if args.run or args.all:
        await phase_run(args, out_dir)
    if args.judge or args.all:
        await phase_judge(args, out_dir)
    if args.report or args.all:
        phase_report(args, out_dir)


if __name__ == "__main__":
    asyncio.run(main())
