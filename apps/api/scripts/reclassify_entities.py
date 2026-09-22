#!/usr/bin/env python3
"""
thing 实体重分类（把历史 thing 按最新 15 类重新打标）

背景（2026-09-22）：旧 prompt 的类型枚举写死 4 类，导致 18.8k 个实体全被塞进 `thing`
（实测 100% 有记忆链接、只有 11 个会被今天规则判垃圾 ⇒ 是"当年没法分类的真实实体"）。
本脚本只对**高频头部**重打类型（默认 links≥5），尾部（81% 只被提及一次）保持不动。

⚠️ Review 发现的两个硬约束（本脚本据此设计）：
1. `entities` 有 **UNIQUE(name, type, container_tag)**，且 `_store_entity_graph` 是按该
   **三元组** get-or-create 的 ⇒ **type 属于身份键**。若目标类型已存在同容器同名行，
   直接 UPDATE 会违反约束 ⇒ 本脚本**跳过有同名兄弟的行**（只处理无兄弟的干净子集），
   并把跳过的量报出来（那部分属"实体去重/合并"任务，不是重分类）。
2. 类型不参与召回（唯一消费点是类型归一化 + /graph 筛选 + stats 展示）⇒ 收益是可读性；
   因此**宁可少改、不可错改**：分类跑两遍取一致 + 独立模型盲评达标才落库。

安全设计：
- 默认 **dry-run**（只分类 + 盲评 + 报告，不写库）
- 落库前**必须**盲评准确率 ≥ `--min-accuracy`（默认 0.85），否则中止且不写任何行
- 写前备份 (id, name, old_type, container_tag) → `backups/reclassify-<ts>.json`
- 只 UPDATE `entities.type`，不动 name/链接/关系；自带 `--rollback <backup.json>`

用法:
    cd apps/api
    python scripts/reclassify_entities.py                 # 预览：分类+盲评+报告
    python scripts/reclassify_entities.py --apply         # 达标才写库
    python scripts/reclassify_entities.py --rollback backups/reclassify-20260922-xxxx.json
"""

import argparse
import asyncio
import json
import os
import sys
from collections import Counter
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx  # noqa: E402

from src.config import settings  # noqa: E402
from src.database import db  # noqa: E402
from src.services.graph_tools import ENTITY_TYPES  # noqa: E402

# 与 prompt 同一套语义（prompt 用自然语言描述，这里给分类器用的紧凑版）
TYPE_GUIDE = {
    "person": "具体人物（张三）",
    "organization": "具体组织/公司（字节跳动）",
    "location": "具体地点（北京）",
    "event": "事件（某次迁移/事故）",
    "preference": "偏好（喜欢暗黑模式）",
    "thing": "不属于以下任何一类、但可命名的具体事物（**不确定就用这个**）",
    "software": "软件/工具/客户端（dsh、opencodex、PostgreSQL、Cursor）",
    "system": "系统/平台/环境（WSL2、PVE、Chrome、tailnet）",
    "service": "服务/进程/端点（gunicorn、sshd）",
    "config": "配置项/参数/策略/开关（volatile-lru、timeout=120、reasoning_effort）",
    "version": "版本号/发行版（Debian 12、pgvector 0.8.2）",
    "protocol": "协议/接口/标准（HTTP、SSH、CTP、SMB、JSON schema）",
    "technology": "技术/框架/库/算法（pgvector、jieba、asyncpg、MACD）",
    "metric": "指标/度量（IC 值、命中率、Recall@k）",
    "concept": "概念/模式/方法论（fail-open、影子调用、LRU）",
}
JUDGE_MODEL = "commandcode/Qwen/Qwen3.7-Max"


def _assert_taxonomy_in_sync():
    unknown = set(TYPE_GUIDE) - set(ENTITY_TYPES)
    assert not unknown, f"分类器类型清单超出白名单（会被压成 thing）: {unknown}"


async def fetch_candidates(min_links: int):
    """候选 = thing 且 links≥阈值 且 **无同名兄弟行**（避免撞唯一约束）。"""
    rows = await db.fetch(
        """
        SELECT e.id, e.name, e.container_tag,
               (SELECT count(*) FROM memory_entities me WHERE me.entity_id = e.id) AS links,
               (SELECT count(*) FROM entities e2
                 WHERE lower(trim(e2.name)) = lower(trim(e.name)) AND e2.container_tag = e.container_tag) AS siblings,
               COALESCE(
                 (SELECT left(m.content, 200) FROM memory_entities me JOIN memories m ON m.id = me.memory_id
                   WHERE me.entity_id = e.id AND m.content ILIKE '%' || e.name || '%'
                   ORDER BY m.created_at DESC LIMIT 1),
                 (SELECT left(m.content, 200) FROM memory_entities me JOIN memories m ON m.id = me.memory_id
                   WHERE me.entity_id = e.id ORDER BY m.created_at DESC LIMIT 1)
               ) AS snippet
        FROM entities e
        WHERE e.type = 'thing'
        """,
    )
    head = [r for r in rows if r["links"] >= min_links]
    clean = [r for r in head if r["siblings"] == 1]
    skipped = [r for r in head if r["siblings"] > 1]
    return clean, skipped, len(rows)


async def _chat(model, messages, max_tokens=8000, effort="low"):
    body = {"model": model, "messages": messages, "temperature": 0.3, "max_tokens": max_tokens}
    if effort and "commandcode" in model:
        body["reasoning_effort"] = effort
    async with httpx.AsyncClient(timeout=300) as c:
        r = await c.post(f"{settings.OPENCODEX_API_BASE}/chat/completions",
                         headers={"Authorization": "Bearer " + (settings.OPENCODEX_API_KEY or "")}, json=body)
    if r.status_code != 200:
        return None
    return r.json()["choices"][0]["message"].get("content") or ""


def _parse_json_array(text):
    if not text:
        return None
    s = text.strip()
    if "```" in s:
        s = s[s.find("["): s.rfind("]") + 1]
    try:
        d = json.loads(s)
        return d if isinstance(d, list) else None
    except Exception:
        return None


async def classify_batch(items):
    """items: [(idx, name, snippet)] → {idx: type}"""
    listing = "\n".join(f"{i}. {name}   ← 出处片段：{ (sn or '')[:90] }" for i, name, sn in items)
    types = "\n".join(f"- {t}: {d}" for t, d in TYPE_GUIDE.items())
    prompt = f"""你是实体类型标注员。下面每个条目给了一个**实体名**和它出现的**记忆片段**，请为每个实体选一个最合适的类型。

【可选类型】
{types}

【待标注】
{listing}

只输出 JSON 数组，每个元素形如 {{"i": 序号, "type": "类型"}}。不要输出其他文字。

⚠️ 判定规则：
- **片段里能看到这个实体是怎么用的**，才按用处选类型；
- 片段看不懂 / 与实体无关 / 拿不准，就填 `thing`（宁缺勿错，保持 thing 无害）；
- 名字像但片段没支持（例如名字是"半导体"而片段讲稀土），填 `thing`。"""
    content = await _chat(settings.OPENCODEX_LLM_MODEL, [
        {"role": "system", "content": "你是严谨的数据标注员，只输出 JSON。"},
        {"role": "user", "content": prompt}], max_tokens=8000)
    arr = _parse_json_array(content) or []
    out = {}
    for it in arr:
        if isinstance(it, dict) and isinstance(it.get("i"), int) and it.get("type") in TYPE_GUIDE:
            out[it["i"]] = it["type"]
    return out


async def classify_all(cands, batch_size, rounds=2):
    """跑 rounds 遍，只保留**两遍一致且不是 thing** 的结果。"""
    results = []
    for r in range(rounds):
        got = {}
        for s in range(0, len(cands), batch_size):
            chunk = cands[s:s + batch_size]
            got.update(await classify_batch([(s + k, c["name"], c["snippet"]) for k, c in enumerate(chunk)]))
            print(f"    第 {r+1} 轮 {min(s+batch_size, len(cands))}/{len(cands)}", flush=True)
        results.append(got)
    agreed = {}
    for i, c in enumerate(cands):
        a, b = results[0].get(i), results[1].get(i)
        if a and b and a == b and a != "thing":
            agreed[i] = a
    return agreed, results


async def judge_sample(pairs):
    """独立模型盲评：给同样的 名字+片段，判断标注是否合适（batch 10/次）。"""
    verdicts = []
    for s in range(0, len(pairs), 10):
        chunk = pairs[s:s + 10]
        listing = "\n".join(f"{k}. 实体「{c['name']}」标为 {t}   ← 片段：{(c['snippet'] or '')[:90]}"
                            for k, (c, t) in enumerate(chunk))
        prompt = f"""下面是把实体名标注为某类型的若干判断。请逐条判断该标注是否**合理**（依据名字与出现片段）。

{listing}

只输出 JSON 数组：{{"k": 序号, "ok": true/false, "why": "极简理由"}}；信息不足无法判断时 ok 填 null。"""
        content = await _chat(JUDGE_MODEL, [
            {"role": "system", "content": "你是严格的数据质量评审，只输出 JSON。"},
            {"role": "user", "content": prompt}], max_tokens=8000, effort=None)
        arr = _parse_json_array(content) or []
        for it in arr:
            if isinstance(it, dict) and isinstance(it.get("k"), int) and it["k"] < len(chunk):
                verdicts.append((chunk[it["k"]], it.get("ok"), it.get("why", "")))
    return verdicts


async def rollback(path):
    data = json.load(open(path))
    for row in data["changes"]:
        await db.execute("UPDATE entities SET type = $1 WHERE id = $2", row["old_type"], row["id"])
    print(f"已回滚 {len(data['changes'])} 行 → 类型恢复为改动前的值")


async def main():
    ap = argparse.ArgumentParser(description="thing 实体重分类（默认 dry-run）")
    ap.add_argument("--dry-run", action="store_true", help="预览（默认行为）")
    ap.add_argument("--apply", action="store_true", help="达标后写库")
    ap.add_argument("--min-links", type=int, default=5, help="只处理链接数≥该值的头部实体（默认 5）")
    ap.add_argument("--batch-size", type=int, default=25)
    ap.add_argument("--eval-sample", type=int, default=30, help="盲评抽样条数")
    ap.add_argument("--min-accuracy", type=float, default=0.85, help="盲评达标线（低于则拒绝写库）")
    ap.add_argument("--backup-dir", default="backups")
    ap.add_argument("--rollback", help="按备份文件回滚")
    args = ap.parse_args()

    _assert_taxonomy_in_sync()
    await db.connect()
    try:
        if args.rollback:
            await rollback(args.rollback)
            return 0

        cands, skipped, thing_total = await fetch_candidates(args.min_links)
        print(f"thing 总数 {thing_total}｜links≥{args.min_links} 的头部 {len(cands)+len(skipped)} 个"
              f"（可安全改 {len(cands)}，因有同名兄弟跳过 {len(skipped)}）\n")
        if not cands:
            print("无可处理候选")
            return 0

        print("① 分类（两遍取一致，不确定保持 thing）")
        agreed, _ = await classify_all(cands, args.batch_size)
        print(f"   一致且非 thing 的: {len(agreed)}/{len(cands)}")
        print("   目标类型分布:", dict(Counter(agreed.values()).most_common()))

        if not agreed:
            print("没有达成一致的标注，中止（未写库）")
            return 0

        pairs_all = [(cands[i], t) for i, t in agreed.items()]
        sample = pairs_all[: args.eval_sample]
        print(f"\n② 盲评抽样 {len(sample)} 条（{JUDGE_MODEL}）")
        verdicts = await judge_sample(sample)
        ok = sum(1 for _, v, _ in verdicts if v is True)
        bad = sum(1 for _, v, _ in verdicts if v is False)
        unk = sum(1 for _, v, _ in verdicts if v is None)
        acc = ok / (ok + bad) if (ok + bad) else 0.0
        print(f"   合理 {ok}｜不合理 {bad}｜无法判断 {unk} ⇒ 准确率 {acc:.0%}（达标线 {args.min_accuracy:.0%}）")
        for (c, t), v, why in verdicts:
            if v is False:
                print(f"     ✗ {c['name'][:24]} → {t}：{why[:50]}")

        if not args.apply:
            print("\n（dry-run，未写库）")
            return 0
        if acc < args.min_accuracy:
            print(f"\n❌ 准确率 {acc:.0%} < {args.min_accuracy:.0%}，拒绝写库")
            return 2

        path = os.path.join(args.backup_dir, f"reclassify-{datetime.now():%Y%m%d-%H%M%S}.json")
        os.makedirs(args.backup_dir, exist_ok=True)
        changes = [{"id": c["id"], "name": c["name"], "container_tag": c["container_tag"],
                    "old_type": "thing", "new_type": t} for c, t in pairs_all]
        json.dump({"created_at": datetime.now().isoformat(), "accuracy": acc, "changes": changes},
                  open(path, "w"), ensure_ascii=False)
        try:
            os.chmod(path, 0o644)
        except OSError:
            pass
        print(f"\n③ 写库（备份 → {path}）")
        async with db.transaction() as conn:
            for ch in changes:
                await db.execute("UPDATE entities SET type = $1 WHERE id = $2 AND type = 'thing'",
                                 ch["new_type"], ch["id"], conn=conn)
        left = await db.fetchval("SELECT count(*) FROM entities WHERE type='thing'")
        print(f"   完成 {len(changes)} 行｜thing 余量 {thing_total} → {left}")
        print(f"   回滚：python scripts/reclassify_entities.py --rollback {path}")
        print(f"\n⚠️ 另有 {len(skipped)} 个头部实体因**存在同名兄弟行**被跳过 —— 那属于"
              f"「实体去重/合并」任务（全库 424 组同名多型），需要单独决策")
        return 0
    finally:
        await db.disconnect()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
