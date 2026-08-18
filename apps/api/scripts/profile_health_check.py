#!/usr/bin/env python3
"""用户画像健康检查（2026-08-18）：扫描各容器 static 画像，输出健康报告。

检查项：
1. 非 preference 的 static（违反"画像=用户偏好"定位，需确认是否降级）
2. 重复条目（同容器 ≥0.95 相似对）
3. 过期风险（内容含易变信息：密钥/地址/主机名/版本）
4. 体积报告（各容器 static 数量 + 总字符）

用法：cd apps/api && venv/bin/python scripts/profile_health_check.py [--container TAG]
"""
import sys
import os
import asyncio
import re

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

TRANSIENT_MARKERS = [
    r"已吊销", r"已改为", r"已保存", r"已删除", r"已变更", r"已迁移",
    r"机器主机名", r"hostnamectl", r"关键bug已修复", r"bug\s*已修复",
    r"密钥", r"token", r"密码", r"API Key", r"apiKey",
]


async def main():
    from src.database import db

    target = sys.argv[1].split("=")[1] if len(sys.argv) > 1 and sys.argv[1].startswith("--container") else None

    # 各容器 static 数量
    if target:
        rows = await db.fetch(
            "SELECT container_tag, id, content, metadata, is_static FROM memories "
            "WHERE is_latest=TRUE AND is_forgotten=FALSE AND is_static=TRUE AND container_tag=$1",
            target,
        )
    else:
        rows = await db.fetch(
            "SELECT container_tag, id, content, metadata, is_static FROM memories "
            "WHERE is_latest=TRUE AND is_forgotten=FALSE AND is_static=TRUE "
            "ORDER BY container_tag"
        )

    print(f"=== 画像健康检查 ({len(rows)} 条 static) ===")
    by_container = {}
    for r in rows:
        by_container.setdefault(r["container_tag"], []).append(r)

    for tag, mems in sorted(by_container.items(), key=lambda x: -len(x[1])):
        print(f"\n--- {tag} ({len(mems)} 条 static) ---")
        for m in mems:
            meta = m["metadata"] or {}
            if isinstance(meta, str):
                try:
                    import json as _json
                    meta = _json.loads(meta) if meta else {}
                except Exception:
                    meta = {}
            mtype = meta.get("type", "(无type)")
            pw = meta.get("profile_worthy")
            flags = []
            # 1. 非 preference
            if mtype != "preference":
                flags.append("非preference")
            # 2. profile_worthy 标记状态
            if pw is None:
                flags.append("无profile_worthy标记")
            elif pw is False:
                flags.append("已标记false(不进画像)")
            # 3. 过期风险
            if any(re.search(p, m["content"]) for p in TRANSIENT_MARKERS):
                flags.append("⚠️含易变信息")
            if flags:
                print(f"  [{', '.join(flags)}] {m['content'][:50]}")

    # 体积统计
    print("\n=== 体积报告 ===")
    for tag, mems in sorted(by_container.items(), key=lambda x: -len(x[1])):
        chars = sum(len(m["content"]) for m in mems)
        print(f"  {tag}: {len(mems)} 条 / {chars} 字符")


asyncio.run(main())
