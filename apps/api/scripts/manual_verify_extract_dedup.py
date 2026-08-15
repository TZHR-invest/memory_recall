"""手工验证 B1：/extract-memory 蒸馏去重真实链路（连真实 DB + LLM）。

用法：cd apps/api && venv/bin/python scripts/manual_verify_extract_dedup.py
验证后清理测试容器记忆。
"""
import sys, os, asyncio
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

async def main():
    from src.api.memories import extract_memory_from_summary, ExtractMemoryRequest
    from src.services.core.memory_store import memory_store
    from src.database import db

    tag = f"verify-dedup-{int(asyncio.get_event_loop().time() * 1000) % 1000000}"
    print("测试容器:", tag)
    # 1) 基准记忆（同步写入，立即可检索）
    base_content = "Tailscale 远程访问该服务的地址是 http://100.83.225.105:3080"
    mem = await memory_store.create(
        content=base_content, container_tag=tag,
        generate_embedding=True, extract_entities=False, auto_relations=False,
    )
    print("基准记忆:", mem.id)

    # 2) 蒸馏请求：摘要里包含与基准记忆语义相同的表述
    summary = "排障中验证了一个访问方式：通过 Tailscale 远程访问该服务时地址为 http://100.83.225.105:3080，实测可用且稳定"
    resp = await extract_memory_from_summary(
        ExtractMemoryRequest(summary=summary, language="zh_CN"), container_tag=tag
    )
    print("memories:", [m.content for m in resp.memories])
    print("has_worthwhile:", resp.has_worthwhile)
    print("dropped:", resp.dropped)
    assert len(resp.dropped) >= 1, "应至少丢弃 1 条与基准记忆近似的候选"
    print("✓ B1 真实链路验证通过")

    # 3) 清理
    await db.execute("DELETE FROM memories WHERE container_tag = $1", tag)
    print("已清理测试数据")

asyncio.run(main())
