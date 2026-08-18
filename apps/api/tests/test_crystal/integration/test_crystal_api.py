"""
crystal 集成测试（Postgres + pgvector + schema，test-strategy §1 集成层）

纪律（test-strategy §2 / MR-024 教训）：
- 单文件内全部用例，模块级 fixture 独立连接，禁止跨文件共享 db 单例
- 测试库 memory_recall_test：本文件自建（连 postgres 默认库 CREATE DATABASE IF NOT EXISTS）
- 数据隔离：crystal 测试 owner 用固定测试 key（crystal_test_*），不污染真实容器
- 测试数据不清理（v5 约定；人工清理见 STATUS 测试容器清理史）
"""

import asyncio
import os
from pathlib import Path

import asyncpg
import pytest
from httpx import ASGITransport, AsyncClient

from src.config import settings

TEST_DB = "memory_recall_test"
API_DIR = Path(__file__).resolve().parents[3]  # apps/api


@pytest.fixture(scope="module")
def test_db():
    """重建测试库 + 全量 schema + 指向测试库的 db 单例就绪。

    测试库可销毁重建（与生产库不同）：每次跑都 DROP+CREATE 保证幂等，
    规避 schema.sql v5 段非幂等 ALTER ADD CONSTRAINT 的重复报错。
    """
    # 1. 重建测试库（连 postgres 默认库）
    async def _ensure_db():
        conn = await asyncpg.connect(
            host=settings.DATABASE_HOST,
            port=settings.DATABASE_PORT,
            user=settings.DATABASE_USER,
            password=settings.DATABASE_PASSWORD,
            database="postgres",
        )
        try:
            await conn.execute(f'DROP DATABASE IF EXISTS "{TEST_DB}"')
            await conn.execute(f'CREATE DATABASE "{TEST_DB}"')
        finally:
            await conn.close()

    # 2. 全量 schema（v5 + crystal 段；新库无约束冲突）
    async def _init_schema():
        conn = await asyncpg.connect(
            host=settings.DATABASE_HOST,
            port=settings.DATABASE_PORT,
            user=settings.DATABASE_USER,
            password=settings.DATABASE_PASSWORD,
            database=TEST_DB,
        )
        try:
            sql = (API_DIR / "schema.sql").read_text(encoding="utf-8")
            await conn.execute(sql)
        finally:
            await conn.close()

    async def _run():
        await _ensure_db()
        await _init_schema()

    asyncio.run(_run())

    # 3. 让全局 db 单例指向测试库
    settings.DATABASE_NAME = TEST_DB
    yield TEST_DB


@pytest.fixture(scope="module")
async def client(test_db):
    """ASGI 客户端（lifespan 自动连测试库）。"""
    from main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport, base_url="http://test", timeout=30
    ) as c:
        yield c


@pytest.fixture(scope="module")
async def test_key(client):
    """创建 crystal 测试 owner（is_test=True，crystal_test_* 命名）。"""
    from src.api.auth import AuthService

    auth = AuthService()
    result = await auth.create_key(
        user_id="crystal-test-user",
        user_name="crystal 集成测试",
        name="crystal_test_integration",
        permissions=["read", "write", "delete", "admin"],
        is_test=True,
    )
    yield {"api_key": result.key, "key_id": str(result.id)}


# ==================== schema 对照断言（M1 出口：schema 与 design 一致） ====================


class TestSchemaMatchesDesign:
    """entity-attributes.md 定稿 ↔ schema.sql 逐表逐列断言（test-strategy §5 M1 出口）"""

    EXPECTED_TABLES = {
        "evidence": {
            "id": "text",
            "observed_at": "timestamp with time zone",
            "source_kind": "text",
            "content": "text",
            "scope": "text",
            "owner_type": "text",
            "owner_id": "text",
            "source_ref": "jsonb",
            "extraction_type": "text",
            "idempotency_key": "text",
            "embedding": "USER-DEFINED",
            "created_at": "timestamp with time zone",
        },
        "evidence_processing": {
            "evidence_id": "text",
            "processing_state": "text",
            "current_step": "text",
            "last_error": "jsonb",
            "updated_at": "timestamp with time zone",
        },
        "claim": {
            "id": "text",
            "statement": "text",
            "claim_kind": "text",
            "content_confidence": "double precision",
            "scope": "text",
            "owner_type": "text",
            "owner_id": "text",
            "status": "text",
            "embedding": "USER-DEFINED",
            "created_at": "timestamp with time zone",
        },
        "lineage_edge": {
            "id": "text",
            "from_claim_id": "text",
            "to_claim_id": "text",
            "edge_type": "text",
            "reason": "text",
            "created_at": "timestamp with time zone",
        },
        "claim_activity": {
            "id": "text",
            "claim_id": "text",
            "action": "text",
            "actor_type": "text",
            "actor_id": "text",
            "triggered_by_evidence_id": "text",
            "detail": "jsonb",
            "created_at": "timestamp with time zone",
        },
        "claim_evidence": {
            "claim_id": "text",
            "evidence_id": "text",
            "role": "text",
            "created_at": "timestamp with time zone",
        },
        "claim_usage": {
            "claim_id": "text",
            "reuse_count": "integer",
            "outcome_good": "integer",
            "outcome_bad": "integer",
            "last_used_at": "timestamp with time zone",
            "updated_at": "timestamp with time zone",
        },
    }

    @pytest.mark.anyio
    async def test_all_crystal_tables_exist_with_columns(self, test_db):
        from src.database import db

        rows = await db.fetch(
            """SELECT table_name, column_name, data_type
               FROM information_schema.columns
               WHERE table_schema='crystal'"""
        )
        by_table: dict = {}
        for r in rows:
            by_table.setdefault(r["table_name"], {})[r["column_name"]] = r["data_type"]

        assert set(by_table.keys()) == set(self.EXPECTED_TABLES.keys()), (
            f"表集合不一致: {set(by_table.keys()) ^ set(self.EXPECTED_TABLES.keys())}"
        )
        for table, cols in self.EXPECTED_TABLES.items():
            actual = by_table[table]
            assert set(cols.keys()) == set(actual.keys()), (
                f"{table} 列不一致: 缺 {set(cols) - set(actual)} / 多 {set(actual) - set(cols)}"
            )
            for col, dtype in cols.items():
                assert actual[col] == dtype, f"{table}.{col}: 期望 {dtype} 实得 {actual[col]}"

    @pytest.mark.anyio
    async def test_crystal_enums_and_constraints(self, test_db):
        from src.database import db

        # CHECK 约束抽查：evidence.source_kind 枚举
        rows = await db.fetch(
            """SELECT tc.table_name, pg_get_constraintdef(con.oid) AS def
               FROM pg_constraint con
               JOIN pg_class rel ON rel.oid = con.conrelid
               JOIN pg_namespace ns ON ns.oid = rel.relnamespace
               JOIN information_schema.table_constraints tc
                 ON tc.constraint_name = con.conname AND tc.table_schema='crystal'
               WHERE con.contype='c' AND tc.table_name IN
                 ('evidence','evidence_processing','claim','lineage_edge','claim_activity','claim_evidence')"""
        )
        defs = " ".join(r["def"] for r in rows)
        for expected in [
            "source_kind",
            "agent_add",
            "user_correction",
            "claim_kind",
            "learned-pattern",
            "edge_type",
            "supersedes",
            "retract",
            "actor_type",
            "processing_state",
        ]:
            assert expected in defs, f"缺少 CHECK 约束元素: {expected}"

    @pytest.mark.anyio
    async def test_crystal_indexes(self, test_db):
        from src.database import db

        rows = await db.fetch(
            """SELECT indexname, indexdef FROM pg_indexes WHERE schemaname='crystal'"""
        )
        indexdefs = " ".join(r["indexdef"] for r in rows)
        # 关键索引存在性（entity-attributes §2/§4/§5）
        for expected in [
            "idx_crystal_evidence_owner",
            "idx_crystal_evidence_scope",
            "idx_crystal_evidence_observed",
            "idx_crystal_evidence_idempotency",
            "idx_crystal_evidence_processing_state",
            "idx_crystal_claim_owner",
            "idx_crystal_claim_status",
            "idx_crystal_claim_embedding_active",
            "uq_crystal_lineage_permanent",
            "idx_crystal_activity_claim",
        ]:
            assert any(expected in r["indexname"] for r in rows), f"缺少索引: {expected}"
        # partial HNSW on active claim（indexdef 里 WHERE 带 ::text cast）
        assert any(
            "status = 'active'::text" in r["indexdef"] or "status = 'active'" in r["indexdef"]
            for r in rows
        ), "claim 缺 partial HNSW (WHERE status='active')"


# ==================== evidence API（A1/A2 骨架） ====================


class TestEvidenceAPI:
    @pytest.mark.anyio
    async def test_create_evidence_202_pending(self, client, test_key):
        resp = await client.post(
            "/api/v2/evidence",
            headers={"X-API-Key": test_key["api_key"]},
            json={
                "content": "正式规划文档是 docs/PROJECT_PLAN.md",
                "source_kind": "agent_add",
                "scope": "project-memory_recall",
                "source_ref": {"session_id": "s-01", "message_id": "m-03", "plugin": "dsh"},
                "extraction_type": "verbatim",
            },
        )
        assert resp.status_code == 202
        body = resp.json()
        assert body["code"] == 0
        assert body["data"]["accepted"] is True
        assert body["data"]["processing_state"] == "pending"
        assert body["data"]["current_step"] == "embedding"
        assert body["data"]["evidence_id"].startswith("ev_")

    @pytest.mark.anyio
    async def test_create_evidence_idempotent_hit(self, client, test_key):
        payload = {
            "content": "幂等键测试内容",
            "source_kind": "agent_add",
            "scope": "project-memory_recall",
            "source_ref": {"session_id": "s-99", "message_id": "m-99"},
        }
        r1 = await client.post(
            "/api/v2/evidence", headers={"X-API-Key": test_key["api_key"]}, json=payload
        )
        r2 = await client.post(
            "/api/v2/evidence", headers={"X-API-Key": test_key["api_key"]}, json=payload
        )
        assert r1.status_code == 202 and r2.status_code == 202
        d1, d2 = r1.json()["data"], r2.json()["data"]
        assert d1["evidence_id"] == d2["evidence_id"]
        assert d1["accepted"] is True and d2["accepted"] is False

    @pytest.mark.anyio
    async def test_create_evidence_invalid_source_kind_400(self, client, test_key):
        resp = await client.post(
            "/api/v2/evidence",
            headers={"X-API-Key": test_key["api_key"]},
            json={"content": "x", "source_kind": "bogus"},
        )
        assert resp.status_code == 400
        assert resp.json()["code"] == 400

    @pytest.mark.anyio
    async def test_create_evidence_scope_with_key_prefix_403(self, client, test_key):
        resp = await client.post(
            "/api/v2/evidence",
            headers={"X-API-Key": test_key["api_key"]},
            json={
                "content": "x",
                "source_kind": "agent_add",
                "scope": f"{test_key['key_id']}_project-x",
            },
        )
        assert resp.status_code == 403

    @pytest.mark.anyio
    async def test_no_key_401(self, client):
        resp = await client.get("/api/v2/evidence")
        assert resp.status_code == 401

    @pytest.mark.anyio
    async def test_evidence_detail_and_source_ref_object(self, client, test_key):
        created = await client.post(
            "/api/v2/evidence",
            headers={"X-API-Key": test_key["api_key"]},
            json={
                "content": "详情测试",
                "source_kind": "agent_add",
                "scope": "project-detail-test",
                "source_ref": {"session_id": "s-10", "message_id": "m-10"},
            },
        )
        ev_id = created.json()["data"]["evidence_id"]
        resp = await client.get(
            f"/api/v2/evidence/{ev_id}",
            headers={"X-API-Key": test_key["api_key"]},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["evidence_id"] == ev_id
        assert data["source_ref"] == {"session_id": "s-10", "message_id": "m-10"}
        assert data["processing"]["state"] == "pending"
        assert data["owner_id"] == test_key["key_id"]

    @pytest.mark.anyio
    async def test_evidence_404(self, client, test_key):
        resp = await client.get(
            "/api/v2/evidence/ev_nonexistent",
            headers={"X-API-Key": test_key["api_key"]},
        )
        assert resp.status_code == 404

    @pytest.mark.anyio
    async def test_evidence_list_pagination_and_scope_filter(self, client, test_key):
        for i in range(3):
            await client.post(
                "/api/v2/evidence",
                headers={"X-API-Key": test_key["api_key"]},
                json={
                    "content": f"分页测试 {i}",
                    "source_kind": "agent_add",
                    "scope": "project-pagination",
                },
            )
        resp = await client.get(
            "/api/v2/evidence?scope=project-pagination&limit=2",
            headers={"X-API-Key": test_key["api_key"]},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data["items"]) == 2
        assert data["has_more"] is True
        assert data["next_cursor"] is not None

        # 第二页
        resp2 = await client.get(
            f"/api/v2/evidence?scope=project-pagination&limit=2&cursor={data['next_cursor']}",
            headers={"X-API-Key": test_key["api_key"]},
        )
        assert resp2.status_code == 200
        data2 = resp2.json()["data"]
        assert len(data2["items"]) == 1
        assert data2["has_more"] is False
        # 无重复
        ids1 = {i["evidence_id"] for i in data["items"]}
        ids2 = {i["evidence_id"] for i in data2["items"]}
        assert ids1.isdisjoint(ids2)

    @pytest.mark.anyio
    async def test_evidence_claims_empty_until_m2(self, client, test_key):
        created = await client.post(
            "/api/v2/evidence",
            headers={"X-API-Key": test_key["api_key"]},
            json={"content": "溯源测试", "source_kind": "agent_add"},
        )
        ev_id = created.json()["data"]["evidence_id"]
        resp = await client.get(
            f"/api/v2/evidence/{ev_id}/claims",
            headers={"X-API-Key": test_key["api_key"]},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["claims"] == []

    @pytest.mark.anyio
    async def test_evidence_cross_owner_isolated(self, client, test_key):
        """A 的 evidence 对 B 不可见（owner_id 隔离）"""
        from src.api.auth import AuthService

        auth = AuthService()
        other = await auth.create_key(
            user_id="crystal-other-user",
            user_name="另一个测试用户",
            name="crystal_test_other",
            permissions=["read", "write"],
            is_test=True,
        )
        created = await client.post(
            "/api/v2/evidence",
            headers={"X-API-Key": test_key["api_key"]},
            json={"content": "隔离测试", "source_kind": "agent_add"},
        )
        ev_id = created.json()["data"]["evidence_id"]
        # B 访问 A 的 evidence → 404（不是 200）
        resp = await client.get(
            f"/api/v2/evidence/{ev_id}",
            headers={"X-API-Key": other.key},
        )
        assert resp.status_code == 404


# ==================== 桩端点（M1 出口：骨架路由鉴权冒烟） ====================


class TestStubEndpoints:
    @pytest.mark.anyio
    async def test_stub_501(self, client, test_key):
        resp = await client.post(
            "/api/v2/search",
            headers={"X-API-Key": test_key["api_key"]},
            json={},
        )
        assert resp.status_code == 501
        assert resp.json()["code"] == 501

    @pytest.mark.anyio
    async def test_stub_requires_auth_401(self, client):
        resp = await client.post("/api/v2/search", json={})
        assert resp.status_code == 401

    @pytest.mark.anyio
    async def test_debug_stub_admin_only(self, client, test_key):
        # is_test=True 的 key 算 admin（api-contract §1.3）
        resp = await client.get(
            "/api/v2/debug/traces", headers={"X-API-Key": test_key["api_key"]}
        )
        assert resp.status_code == 501  # 通过 admin 校验，桩返回 501
