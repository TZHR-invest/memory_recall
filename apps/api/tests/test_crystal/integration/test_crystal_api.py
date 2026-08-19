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
        "migration_state": {
            "run_id": "text",
            "owner_id": "text",
            "total": "integer",
            "migrated": "integer",
            "skipped": "integer",
            "failed": "integer",
            "last_memory_id": "text",
            "status": "text",
            "error": "text",
            "created_at": "timestamp with time zone",
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
        # search/migrate 已在 M2/M3 实现；用仍为桩的 debug 端点测 501
        resp = await client.get(
            "/api/v2/debug/traces",
            headers={"X-API-Key": test_key["api_key"]},
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


# ==================== M2：对账闭环（写路径，A1/A2/A3） ====================
# LLM 依赖隔离（test-strategy §3）：mock aextract_json + embedding
# 对账函数直接调用（不经 worker，worker 异步时序不可控）


@pytest.fixture
def mock_llm(monkeypatch):
    """mock LLM：碰撞判定 + claim_kind 判定（test-strategy §3 LLM 依赖隔离）"""
    from src.api.crystal import reconcile_service

    async def fake_aextract_json(prompt, temperature=0.0, max_tokens=2000):
        if "判断新证据与已有主张" in prompt:
            # 碰撞判定：第一条候选 SUPPORT，其余 UNRELATED
            return {
                "relations": [
                    {"claim_id": "cl_target_1", "judgment": "SUPPORT", "reason": "支持"},
                    {"claim_id": "cl_target_2", "judgment": "UNRELATED", "reason": "无关"},
                ]
            }
        if "claim_kind 四选一" in prompt:
            return {"claim_kind": "fact", "statement": "对账测试断言"}
        return {}

    monkeypatch.setattr(reconcile_service, "_llm_collision_judge", _fake_collision)
    monkeypatch.setattr(reconcile_service, "_llm_claim_kind_and_statement", _fake_kind)
    yield


@pytest.fixture
def mock_embedding(monkeypatch):
    """mock embedding：确定性 1024 维向量（同内容同向量，支持向量检索命中）"""
    from src.api.crystal import reconcile_service

    async def fake_embed(text):
        import hashlib

        digest = hashlib.sha256(text.encode()).digest()
        vec = [(b / 255.0) * 2 - 1 for b in digest]
        vec = (vec * 64)[:1024]  # 扩展到 1024 维
        return vec

    monkeypatch.setattr(reconcile_service, "_embed", fake_embed)
    yield


async def _fake_collision(evidence, candidates):
    """碰撞判定替身：SUPPORT 第一条候选（若有），否则空"""
    if candidates:
        return [
            {
                "claim_id": candidates[0]["id"],
                "judgment": "SUPPORT",
                "reason": "测试替身",
            }
        ]
    return []


async def _fake_kind(content, source_kind, old_claim_kind=None):
    """claim_kind/statement 替身"""
    if source_kind == "user_correction" and old_claim_kind:
        return old_claim_kind, content
    return "fact", content


class TestReconcileFlow:
    @pytest.mark.anyio
    async def test_evidence_reconcile_creates_claim(self, test_db, test_key, mock_llm, mock_embedding):
        """写 evidence → 对账 → 生成 claim + claim_evidence（A1/A2）"""
        from src.api.crystal.reconcile_service import reconcile_evidence

        # 先落 evidence（直接 SQL，模拟 POST 落库）
        from src.database import db

        ev_id = await db.fetchval(
            """INSERT INTO crystal.evidence
               (observed_at, source_kind, content, scope, owner_type, owner_id,
                source_ref, extraction_type, created_at)
               VALUES (NOW(), 'agent_add', 'M2 对账测试：项目使用 FastAPI', 'project-m2',
                       'personal', $1, '{"session_id":"s-m2-1","message_id":"m-m2-1"}'::jsonb,
                       'verbatim', NOW())
               RETURNING id""",
            test_key["key_id"],
        )
        await db.execute(
            """INSERT INTO crystal.evidence_processing
               (evidence_id, processing_state, current_step, updated_at)
               VALUES ($1, 'pending', 'embedding', NOW())""",
            ev_id,
        )

        result = await reconcile_evidence(ev_id)

        assert result["status"] == "done"
        # 无候选 → 建新 claim
        assert result["created_claim_id"] is not None

        claim_id = result["created_claim_id"]
        # 不变量①：claim 必有 claim_evidence
        link_count = await db.fetchval(
            "SELECT COUNT(*) FROM crystal.claim_evidence WHERE claim_id=$1", claim_id
        )
        assert link_count >= 1
        # status=active + claim_kind=fact
        claim = await db.fetchrow(
            "SELECT statement, claim_kind, status, content_confidence FROM crystal.claim WHERE id=$1",
            claim_id,
        )
        assert claim["status"] == "active"
        assert claim["claim_kind"] == "fact"
        # evidence_processing done
        state = await db.fetchval(
            "SELECT processing_state FROM crystal.evidence_processing WHERE evidence_id=$1",
            ev_id,
        )
        assert state == "done"

    @pytest.mark.anyio
    async def test_evidence_reconcile_reinforces_existing_claim(self, test_db, test_key, mock_llm, mock_embedding):
        """已有 claim → 新 evidence SUPPORT → reinforce（不建新 claim，追加关联 + 计分）"""
        from src.api.crystal.reconcile_service import reconcile_evidence
        from src.database import db

        # 建一个初始 claim
        claim_id = await db.fetchval(
            """INSERT INTO crystal.claim
               (statement, claim_kind, content_confidence, scope, owner_type, owner_id,
                status, created_at)
               VALUES ('已有断言：项目使用 FastAPI', 'fact', 0.5, 'project-reinforce',
                       'personal', $1, 'active', NOW())
               RETURNING id""",
            test_key["key_id"],
        )

        # 新 evidence（与 claim 相关 → 替身判定 SUPPORT）
        ev_id = await db.fetchval(
            """INSERT INTO crystal.evidence
               (observed_at, source_kind, content, scope, owner_type, owner_id,
                source_ref, extraction_type, created_at)
               VALUES (NOW(), 'agent_add', '补充：FastAPI 用于后端', 'project-reinforce',
                       'personal', $1, '{"session_id":"s-m2-2","message_id":"m-m2-2"}'::jsonb,
                       'verbatim', NOW())
               RETURNING id""",
            test_key["key_id"],
        )
        await db.execute(
            """INSERT INTO crystal.evidence_processing
               (evidence_id, processing_state, current_step, updated_at)
               VALUES ($1, 'pending', 'embedding', NOW())""",
            ev_id,
        )

        # mock 候选定位：让 _find_candidate_claims 返回该 claim（需要 embedding 命中）
        # 简化：直接给 claim 写 embedding 使向量检索命中
        import hashlib

        digest = hashlib.sha256("补充：FastAPI 用于后端".encode()).digest()
        vec = [(b / 255.0) * 2 - 1 for b in digest]
        vec = (vec * 64)[:1024]
        await db.execute(
            "UPDATE crystal.claim SET embedding=$1 WHERE id=$2",
            "[" + ",".join(str(x) for x in vec) + "]",
            claim_id,
        )

        result = await reconcile_evidence(ev_id)

        assert result["status"] == "done"
        assert result["created_claim_id"] is None
        assert result["reinforced_claim_id"] == claim_id
        # 关联追加
        link_count = await db.fetchval(
            "SELECT COUNT(*) FROM crystal.claim_evidence WHERE claim_id=$1", claim_id
        )
        assert link_count >= 1
        # 置信度提升（reinforce 计分）
        new_conf = await db.fetchval(
            "SELECT content_confidence FROM crystal.claim WHERE id=$1", claim_id
        )
        assert new_conf > 0.5

    @pytest.mark.anyio
    async def test_correct_supersedes_claim(self, test_db, test_key):
        """workbench correct → user_correction Evidence → supersede 边 + 旧 claim superseded（A3）"""
        from src.api.crystal.reconcile_service import reconcile_correction
        from src.database import db

        # 建一个将被纠正的 claim
        old_claim_id = await db.fetchval(
            """INSERT INTO crystal.claim
               (statement, claim_kind, content_confidence, scope, owner_type, owner_id,
                status, created_at)
               VALUES ('错误断言：数据库是 MySQL', 'fact', 0.8, 'project-m2',
                       'personal', $1, 'active', NOW())
               RETURNING id""",
            test_key["key_id"],
        )

        result = await reconcile_correction(
            old_claim_id,
            "正确断言：数据库是 PostgreSQL",
            "personal",
            test_key["key_id"],
            source_ref={"session_id": "s-cor", "message_id": "m-cor"},
            actor_id=test_key["key_id"],
        )

        assert result["superseded_claim_id"] == old_claim_id
        new_claim_id = result["new_claim_id"]

        # 旧 claim superseded
        old_status = await db.fetchval(
            "SELECT status FROM crystal.claim WHERE id=$1", old_claim_id
        )
        assert old_status == "superseded"
        # supersede 边存在
        edge = await db.fetchrow(
            """SELECT edge_type, reason FROM crystal.lineage_edge
               WHERE from_claim_id=$1 AND to_claim_id=$2""",
            old_claim_id,
            new_claim_id,
        )
        assert edge["edge_type"] == "supersedes"
        # 新 claim 引用纠正证据
        ev = await db.fetchrow(
            """SELECT e.source_kind FROM crystal.claim_evidence ce
               JOIN crystal.evidence e ON e.id = ce.evidence_id
               WHERE ce.claim_id=$1""",
            new_claim_id,
        )
        assert ev["source_kind"] == "user_correction"

    @pytest.mark.anyio
    async def test_forget_retracts_claim(self, test_db, test_key):
        """workbench forget → retract 边 + status=retracted"""
        from src.api.crystal.reconcile_service import reconcile_forget
        from src.database import db

        claim_id = await db.fetchval(
            """INSERT INTO crystal.claim
               (statement, claim_kind, scope, owner_type, owner_id, status, created_at)
               VALUES ('要遗忘的断言', 'fact', 'project-m2', 'personal', $1, 'active', NOW())
               RETURNING id""",
            test_key["key_id"],
        )

        result = await reconcile_forget(
            claim_id, "personal", test_key["key_id"], actor_id=test_key["key_id"]
        )
        assert result["status"] == "retracted"
        status = await db.fetchval("SELECT status FROM crystal.claim WHERE id=$1", claim_id)
        assert status == "retracted"
        edge = await db.fetchrow(
            "SELECT edge_type FROM crystal.lineage_edge WHERE from_claim_id=$1 AND to_claim_id IS NULL",
            claim_id,
        )
        assert edge["edge_type"] == "retract"


# ==================== M2：召回读路径（A4/A5） ====================


class TestRecall:
    @pytest.mark.anyio
    async def test_search_returns_active_only_and_explain(self, test_db, test_key, mock_embedding):
        """search 只返回 active + scope 匹配；explain 含粗排/精排/截断（A4/A5）"""
        from src.database import db
        from src.api.crystal.recall_service import search_claims

        # 造数据：2 active + 1 superseded（同 scope）
        for i, (stmt, status) in enumerate(
            [
                ("FastAPI 用于后端开发", "active"),
                ("PostgreSQL 用于存储", "active"),
                ("旧断言已失效", "superseded"),
            ]
        ):
            await db.execute(
                """INSERT INTO crystal.claim
                   (statement, claim_kind, content_confidence, scope, owner_type, owner_id,
                    status, created_at)
                   VALUES ($1, 'fact', 0.7, 'project-search', 'personal', $2, $3, NOW())""",
                stmt,
                test_key["key_id"],
                status,
            )

        result = await search_claims(
            query="FastAPI 后端",
            owner_type="personal",
            owner_id=test_key["key_id"],
            scope="project-m2",
            limit=10,
            include_explain=True,
        )

        # A4：superseded 不混入
        statements = [r["statement"] for r in result["results"]]
        assert "旧断言已失效" not in statements
        assert len(result["results"]) == 2
        # A5：explain 结构
        assert "explain" in result
        explain = result["explain"]
        assert "prefilter" in explain
        assert "candidates" in explain
        assert "ranked" in explain
        assert "truncated" in explain
        assert "low_confidence" in explain

    @pytest.mark.anyio
    async def test_search_scope_isolation(self, test_db, test_key):
        """owner 隔离：他人 claim 不可见（A6）"""
        from src.database import db
        from src.api.crystal.recall_service import search_claims

        # 另一个 owner 的 claim
        await db.execute(
            """INSERT INTO crystal.claim
               (statement, claim_kind, scope, owner_type, owner_id, status, created_at)
               VALUES ('他人的秘密断言', 'fact', 'project-m2', 'personal', 'other-key-id', 'active', NOW())"""
        )

        result = await search_claims(
            query="秘密断言",
            owner_type="personal",
            owner_id=test_key["key_id"],
            scope="project-m2",
            limit=10,
        )
        statements = [r["statement"] for r in result["results"]]
        assert "他人的秘密断言" not in statements

    @pytest.mark.anyio
    async def test_search_api_endpoint(self, client, test_db, test_key, mock_embedding):
        """POST /api/v2/search 端点（api-contract §4.2）"""
        resp = await client.post(
            "/api/v2/search",
            headers={"X-API-Key": test_key["api_key"]},
            json={"query": "FastAPI", "scope": "project-m2", "limit": 5, "include_explain": True},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 0
        assert isinstance(body["data"]["results"], list)
        assert "explain" in body["data"]


# ==================== M2：工作台端点（A6/A7/A8） ====================


class TestWorkbench:
    @pytest.mark.anyio
    async def test_overview_stats(self, test_db, test_key):
        """overview 统计只含个人 owner（A8）"""
        from src.database import db
        from src.api.crystal.workbench import _overview_stats

        # 造数据
        await db.execute(
            """INSERT INTO crystal.claim
               (statement, claim_kind, content_confidence, scope, owner_type, owner_id, status, created_at)
               VALUES ('统计测试断言', 'fact', 0.6, 'project-m2', 'personal', $1, 'active', NOW())""",
            test_key["key_id"],
        )

        stats = await _overview_stats("personal", test_key["key_id"])
        assert "topology" in stats
        assert "value_distribution" in stats
        assert "source_kind_composition" in stats
        assert "processing_health" in stats
        assert stats["topology"]["claims"].get("active", 0) >= 1

    @pytest.mark.anyio
    async def test_workbench_claims_list(self, client, test_db, test_key):
        """workbench/claims 列表（个人 owner）"""
        resp = await client.get(
            "/api/v2/workbench/claims",
            headers={"X-API-Key": test_key["api_key"]},
        )
        assert resp.status_code == 200
        assert isinstance(resp.json()["data"]["items"], list)

    @pytest.mark.anyio
    async def test_workbench_cross_owner_403(self, client, test_db, test_key):
        """他人 claim 不可 confirm（A6 越权）"""
        from src.database import db

        other_claim = await db.fetchval(
            """INSERT INTO crystal.claim
               (statement, claim_kind, scope, owner_type, owner_id, status, created_at)
               VALUES ('他人 claim', 'fact', 'project-m2', 'personal', 'other-key-id', 'active', NOW())
               RETURNING id"""
        )
        resp = await client.post(
            f"/api/v2/workbench/claims/{other_claim}/confirm",
            headers={"X-API-Key": test_key["api_key"]},
            json={},
        )
        assert resp.status_code == 404  # 他人数据不可见 → 404（不泄露存在性）


# ==================== M3：迁移（A9 幂等重放 / 断点续传） ====================


class TestMigration:
    async def _fresh_key(self):
        """创建独立测试 key（迁移测试各自隔离，避免 owner 前缀匹配交叉污染）"""
        from src.api.auth import AuthService

        auth = AuthService()
        result = await auth.create_key(
            user_id="crystal-mig-test",
            user_name="迁移测试",
            name="crystal_test_migration",
            permissions=["read", "write", "delete", "admin"],
            is_test=True,
        )
        return {"api_key": result.key, "key_id": str(result.id)}

    @pytest.mark.anyio
    async def test_migration_idempotent_replay(self, test_db):
        """迁移幂等：跑两次 migrated=0，全部 skipped（A9）"""
        from migrate_memories import (
            migrate_idempotency_key,
            parse_container_tag,
            run_migration,
        )
        from src.database import db

        key = await self._fresh_key()

        # 造 v5 测试记忆（用户级 + 项目级）
        await db.execute(
            """INSERT INTO memories (id, container_tag, content, is_latest, is_forgotten, created_at)
               VALUES ('mig-test-1', $1, '迁移测试记忆A', TRUE, FALSE, NOW())""",
            key["key_id"],
        )
        await db.execute(
            """INSERT INTO memories (id, container_tag, content, is_latest, is_forgotten, created_at)
               VALUES ('mig-test-2', $1, '迁移测试记忆B', TRUE, FALSE, NOW())""",
            f"{key['key_id']}_project-mig-test",
        )
        # 孤儿旧版本不迁移
        await db.execute(
            """INSERT INTO memories (id, container_tag, content, is_latest, is_forgotten, created_at)
               VALUES ('mig-test-3', $1, '孤儿旧版本', FALSE, FALSE, NOW())""",
            key["key_id"],
        )

        # 第一次迁移
        stats1 = await run_migration(owner_id=key["key_id"])
        assert stats1["total"] == 2  # 只有 2 条 active
        assert stats1["migrated"] == 2
        assert stats1["skipped"] == 0
        assert stats1["status"] == "done"

        # 第二次迁移（幂等重放）
        stats2 = await run_migration(owner_id=key["key_id"])
        assert stats2["total"] == 2
        assert stats2["migrated"] == 0
        assert stats2["skipped"] == 2  # 全部幂等命中跳过
        assert stats2["status"] == "done"

        # evidence 落库验证（幂等键）
        ev_count = await db.fetchval(
            "SELECT COUNT(*) FROM crystal.evidence WHERE owner_id=$1",
            key["key_id"],
        )
        assert ev_count == 2
        # 孤儿旧版本不迁移
        idem3 = migrate_idempotency_key("mig-test-3")
        orphan_ev = await db.fetchval(
            "SELECT COUNT(*) FROM crystal.evidence WHERE idempotency_key=$1", idem3
        )
        assert orphan_ev == 0

    @pytest.mark.anyio
    async def test_parse_container_tag(self, test_key):
        """container_tag 解析（migration-script-design §1）"""
        from migrate_memories import parse_container_tag

        keys = {test_key["key_id"]: "user"}
        # 用户级
        assert parse_container_tag(test_key["key_id"], keys) == {
            "scope": None,
            "owner_id": test_key["key_id"],
        }
        # 项目级
        assert parse_container_tag(f"{test_key['key_id']}_project-myapp", keys) == {
            "scope": "project-myapp",
            "owner_id": test_key["key_id"],
        }
        # 无法归属
        assert parse_container_tag("test_perf_container", keys) is None
        assert parse_container_tag("nonexistent-key_project-x", keys) is None

    @pytest.mark.anyio
    async def test_migration_state_tracks_progress(self, test_db):
        """迁移状态落 migration_state（断点续传依据）"""
        from migrate_memories import run_migration
        from src.database import db

        key = await self._fresh_key()

        await db.execute(
            """INSERT INTO memories (id, container_tag, content, is_latest, is_forgotten, created_at)
               VALUES ('mig-state-1', $1, '状态记录测试', TRUE, FALSE, NOW())""",
            key["key_id"],
        )

        stats = await run_migration(owner_id=key["key_id"])
        assert stats["run_id"].startswith("mig_")

        row = await db.fetchrow(
            "SELECT * FROM crystal.migration_state WHERE run_id=$1", stats["run_id"]
        )
        assert row is not None
        assert row["status"] == "done"
        assert row["total"] == 1
        assert row["migrated"] == 1

    @pytest.mark.anyio
    async def test_migrate_endpoint_requires_admin(self, client, test_key):
        """/api/v2/migrate/run 需 admin（is_test=True 的 key 算 admin，A11）"""
        # is_test=True → admin，应该 202；owner_id 指向不存在的 key → 后台迁移 0 条无副作用
        resp = await client.post(
            "/api/v2/migrate/run",
            headers={"X-API-Key": test_key["api_key"]},
            params={"owner_id": "no-such-key-for-test"},
        )
        assert resp.status_code == 202
        assert resp.json()["data"]["run_id"].startswith("mig_")
