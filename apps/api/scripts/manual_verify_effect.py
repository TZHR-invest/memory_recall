"""自动捕获优化 · 效果端到端验证（后端已生效部分，2026-08-16）

场景 1：B1 去重——同主题 5 次蒸馏提交，验证碎片拦截率
场景 2：B2 兜底——_capture 近似写入被异步 DELETE；显式近似写入保留
"""
import sys, os, asyncio, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

async def main():
    from src.api.memories import extract_memory_from_summary, ExtractMemoryRequest
    from src.services.core.memory_store import memory_store
    from src.database import db

    tag = f"085288ba-8eab-439b-b0d4-b92382e0f95d_effect-test-{int(time.time())}"
    print("=== 测试容器:", tag)
    base = "Tailscale 远程访问该服务的地址是 http://100.83.225.105:3080"
    m = await memory_store.create(content=base, container_tag=tag,
        generate_embedding=True, extract_entities=False, auto_relations=False)
    print(f"[基准] {m.id}")

    # ── 场景 1：B1 去重拦截率 ──────────────────────────────
    variants = [
        "排障中验证了通过 Tailscale 远程访问该服务的地址为 http://100.83.225.105:3080，实测可用",
        "这次确认了 Tailscale 方式访问该服务的地址是 http://100.83.225.105:3080，连接稳定",
        "实测 Tailscale 远程连接该服务使用地址 http://100.83.225.105:3080 可正常访问",
        "发现该服务可通过 Tailscale 以 http://100.83.225.105:3080 访问，验证有效",
        "Tailscale 访问该服务的地址 http://100.83.225.105:3080 经测试可用",
    ]
    kept_total = 0
    for i, v in enumerate(variants, 1):
        resp = await extract_memory_from_summary(
            ExtractMemoryRequest(summary=v, language="zh_CN", container_tag=tag),
            current_user={"container_tag": tag, "key_id": "085288ba-8eab-439b-b0d4-b92382e0f95d", "permissions": ["read"]},
        )
        kept_total += len(resp.memories)
        print(f"[蒸馏{i}] kept={len(resp.memories)} dropped={len(resp.dropped)}"
              + (f" 原因: {resp.dropped[0]['reason'][:60]}" if resp.dropped else ""))
    print(f"[场景1] 5 次同主题蒸馏：拦截 {5 - kept_total}/5 条（新增写入 {kept_total} 条）")

    # ── 场景 2：B2 异步兜底 ────────────────────────────────
    dup_content = "Tailscale 远程访问该服务的地址是 http://100.83.225.105:3080"  # 与基准几乎相同
    # 2a: _capture 近似 → 应被异步 DELETE
    from src.api.memories import CreateMemoryRequest, create_memory
    # 直接走 HTTP 等价路径：memory_store.create(async_process 语义由调用方控制)
    captured = await memory_store.create(
        content=dup_content, container_tag=tag,
        metadata={"_capture": True, "type": "learned-pattern"},
        generate_embedding=False, extract_entities=False, auto_relations=False,
    )
    print(f"[场景2a] _capture 近似写入 {captured.id}，等待异步处理...")
    from src.services.core.memory_store import memory_store as ms
    await ms.process_embedding_async(captured.id)  # 模拟 BackgroundTask
    row = await db.fetchrow("SELECT id FROM memories WHERE id = $1", captured.id)
    print(f"[场景2a] 处理后行存在: {row is not None} → {'❌ 未被删除' if row else '✅ 已被物理删除'}")

    # 2b: 显式近似 → 应保留
    explicit = await memory_store.create(
        content=dup_content, container_tag=tag,
        metadata={"type": "learned-pattern"},
        generate_embedding=False, extract_entities=False, auto_relations=False,
    )
    await ms.process_embedding_async(explicit.id)
    row2 = await db.fetchrow("SELECT id FROM memories WHERE id = $1", explicit.id)
    print(f"[场景2b] 显式近似写入 {explicit.id}：处理后行存在: {row2 is not None} → {'✅ 保留（0.95 语义不变）' if row2 else '❌ 被误删'}")

    # 清理
    await db.execute("DELETE FROM memories WHERE container_tag = $1", tag)
    print("=== 已清理测试容器")

asyncio.run(main())
