"""
Backfill missing embeddings for memories and chunks.
Uses Volcengine Ark multimodal embeddings API directly.
"""
import asyncio
import asyncpg
import httpx
import os
import sys

API_KEY = os.environ.get('VOLC_API_KEY')
API_BASE = os.environ.get('VOLC_API_BASE', 'https://ark.cn-beijing.volces.com/api/v3')
EMBEDDING_MODEL = 'doubao-embedding-vision-251215'
DIMENSION = 1024
CONCURRENCY = 3  # concurrent requests

semaphore = asyncio.Semaphore(CONCURRENCY)

async def generate_embedding(text: str, client: httpx.AsyncClient) -> list:
    """Generate embedding using Volcengine multimodal embeddings API."""
    url = f"{API_BASE}/embeddings/multimodal"
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": EMBEDDING_MODEL,
        "input": [{"type": "text", "text": text}],
        "encoding_format": "float",
        "dimensions": DIMENSION,
    }
    try:
        async with semaphore:
            resp = await client.post(url, json=payload, headers=headers, timeout=30.0)
        if resp.status_code != 200:
            print(f"\n  ❌ HTTP {resp.status_code}: {resp.text[:150]}")
            return None
        data = resp.json()
        if "data" in data:
            items = data["data"]
            if isinstance(items, list):
                return items[0]["embedding"]
            return items["embedding"]
        return None
    except Exception as e:
        print(f"\n  ❌ Error: {str(e)[:100]}")
        return None

def emb_to_str(emb: list) -> str:
    return "[" + ",".join(map(str, emb)) + "]"

async def backfill_table(conn, client: httpx.AsyncClient, table: str, label: str):
    rows = await conn.fetch(
        f"SELECT id, content FROM {table} WHERE embedding IS NULL ORDER BY id ASC"
    )
    total = len(rows)
    print(f"\n=== {label}: {total} items ===")
    if total == 0:
        return
    
    success = 0
    for i, row in enumerate(rows):
        sys.stdout.write(f"\r  [{i+1}/{total}] processing...")
        sys.stdout.flush()
        emb = await generate_embedding(row['content'], client)
        if emb:
            await conn.execute(
                f"UPDATE {table} SET embedding = $1::vector WHERE id = $2",
                emb_to_str(emb),
                row['id']
            )
            success += 1
    
    print(f"\n✅ {label}: {success}/{total} done")

async def main():
    if not API_KEY:
        print("❌ VOLC_API_KEY not set")
        sys.exit(1)

    async with httpx.AsyncClient() as client:
        # Test API
        print("🔍 Testing embedding API...")
        test = await generate_embedding("测试", client)
        if test:
            print(f"✅ Embedding API OK (dim={len(test)})")
        else:
            print("❌ Embedding API test failed")
            return

        conn = await asyncpg.connect(
            host='postgres', port=5432, user='postgres',
            password='postgres', database='memory_recall'
        )
        
        try:
            await backfill_table(conn, client, 'memories', 'Memories')
            await backfill_table(conn, client, 'chunks', 'Chunks')

            remain_m = await conn.fetchval("SELECT COUNT(*) FROM memories WHERE embedding IS NULL")
            remain_c = await conn.fetchval("SELECT COUNT(*) FROM chunks WHERE embedding IS NULL")
            print(f"\n📊 剩余无embedding: memories={remain_m}, chunks={remain_c}")
        finally:
            await conn.close()

asyncio.run(main())
