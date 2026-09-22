"""同名家族归一 + 图谱通道确定性（2026-09-22 P0+P1）。

背景（活库实测）：entities 唯一键是 (name, type, container_tag)，type 由 LLM 抽取、
同一实体换个 run 就可能变 ⇒ 424 组同名不同型（856 行），16.2% 的记忆链接挂在非主行上，
且同组两行之间 0 条关系边（互为孤岛）。只看单个 id 就只能看到其中一半。

这些测试锁住四件事：
1. 同名同容器归一族、代表 = 链接最多者（平局取 id 最小）⇒ 确定性；
2. 跨容器绝不归并（租户边界）；
3. 三处接入点确实用了家族（种子排序 / 遍历邻居 / 记忆回查）；
4. ENTITY_FAMILY_EXPANSION=False 时全部回退为单行语义（A/B 与回滚用）。
"""

import os
import sys
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from src.config import settings
from src.services.core.memory_store import MemoryStore


def _entity_row(entity_id: str, name: str = "tailscale", type_: str = "thing"):
    return {
        "id": entity_id,
        "name": name,
        "type": type_,
        "container_tag": "ct_1",
        "mention_count": 1,
        "confidence": 0.9,
        "created_at": None,
        "updated_at": None,
    }


@pytest.fixture
def flag_on():
    old = settings.ENTITY_FAMILY_EXPANSION
    settings.ENTITY_FAMILY_EXPANSION = True
    yield
    settings.ENTITY_FAMILY_EXPANSION = old


@pytest.fixture
def flag_off():
    old = settings.ENTITY_FAMILY_EXPANSION
    settings.ENTITY_FAMILY_EXPANSION = False
    yield
    settings.ENTITY_FAMILY_EXPANSION = old


class TestResolveEntityFamilies:
    def setup_method(self):
        self.store = MemoryStore()

    @pytest.mark.asyncio
    async def test_groups_same_name_into_one_family(self, flag_on):
        """两行同名不同型 → 一个家族，代表 = 链接多的那行（首行即代表）。"""
        rows = [
            {"src_id": "rep", "member_id": "rep", "link_count": 70},
            {"src_id": "rep", "member_id": "sib", "link_count": 21},
            {"src_id": "sib", "member_id": "rep", "link_count": 70},
            {"src_id": "sib", "member_id": "sib", "link_count": 21},
        ]
        with patch("src.services.core.memory_store.db") as mock_db:
            mock_db.fetch = AsyncMock(return_value=rows)
            families = await self.store.resolve_entity_families(["rep"], "ct_1")

        assert list(families.keys()) == ["rep"]
        assert families["rep"] == ["rep", "sib"]  # 代表在前，成员按链接数降序

        # 从次行进入也必须得到同一个家族（否则"看到哪一半"取决于传入的 id）
        with patch("src.services.core.memory_store.db") as mock_db:
            mock_db.fetch = AsyncMock(
                return_value=[
                    {"src_id": "sib", "member_id": "rep", "link_count": 70},
                    {"src_id": "sib", "member_id": "sib", "link_count": 21},
                ]
            )
            families_from_sib = await self.store.resolve_entity_families(["sib"], "ct_1")
        assert list(families_from_sib.keys()) == ["rep"]
        assert families_from_sib["rep"] == ["rep", "sib"]

    @pytest.mark.asyncio
    async def test_family_sql_is_container_scoped(self, flag_on):
        """SQL 必须带同容器约束 —— 容器是租户边界，跨容器合并就是数据串号。"""
        with patch("src.services.core.memory_store.db") as mock_db:
            mock_db.fetch = AsyncMock(return_value=[])
            await self.store.resolve_entity_families(["a"], "ct_1")

        sql = mock_db.fetch.call_args.args[0]
        assert "e2.container_tag = s.container_tag" in sql
        assert "lower(btrim(e2.name)) = s.norm_name" in sql
        # 容器参数以 $2 传入（None 表示不过滤，仅内部调用）
        assert mock_db.fetch.call_args.args[2] == "ct_1"

    @pytest.mark.asyncio
    async def test_empty_input_skips_db(self, flag_on):
        with patch("src.services.core.memory_store.db") as mock_db:
            mock_db.fetch = AsyncMock(return_value=[])
            assert await self.store.resolve_entity_families([], "ct_1") == {}
            assert await self.store.resolve_entity_families([None, ""], "ct_1") == {}
        mock_db.fetch.assert_not_called()


class TestExpandEntityIdsByName:
    def setup_method(self):
        self.store = MemoryStore()

    @pytest.mark.asyncio
    async def test_expands_members_and_keeps_unknown_ids(self, flag_on):
        """家族成员全部返回；库里查不到的 id 原样保留（不静默丢掉调用方的输入）。"""
        with patch.object(
            self.store,
            "resolve_entity_families",
            new_callable=AsyncMock,
            return_value={"rep": ["rep", "sib"]},
        ):
            ids = await self.store.expand_entity_ids_by_name(["rep", "ghost"], "ct_1")
        assert ids == ["rep", "sib", "ghost"]

    @pytest.mark.asyncio
    async def test_no_duplicates_when_both_members_passed(self, flag_on):
        with patch.object(
            self.store,
            "resolve_entity_families",
            new_callable=AsyncMock,
            return_value={"rep": ["rep", "sib"]},
        ):
            ids = await self.store.expand_entity_ids_by_name(["rep", "sib"], "ct_1")
        assert ids == ["rep", "sib"]


class TestGraphPathWiring:
    def setup_method(self):
        self.store = MemoryStore()

    @pytest.mark.asyncio
    async def test_seed_query_ordered_by_cooccurrence(self, flag_on):
        with patch("src.services.core.memory_store.db") as mock_db:
            mock_db.fetch = AsyncMock(return_value=[])
            await self.store.get_entities_for_memories(["mem_1"])

        sql = mock_db.fetch.call_args.args[0]
        assert "COUNT(*) AS co_occur_count" in sql
        assert "ORDER BY co_occur_count DESC, e.mention_count DESC, e.id" in sql

    @pytest.mark.asyncio
    async def test_seed_query_unordered_when_flag_off(self, flag_off):
        """关掉开关 = 旧行为：不排序（回归旧语义，供 A/B 与回滚）。"""
        with patch("src.services.core.memory_store.db") as mock_db:
            mock_db.fetch = AsyncMock(return_value=[])
            await self.store.get_entities_for_memories(["mem_1"])

        sql = mock_db.fetch.call_args.args[0]
        assert "ORDER BY" not in sql

    @pytest.mark.asyncio
    async def test_memory_lookup_expands_family(self, flag_on):
        with patch.object(
            self.store,
            "expand_entity_ids_by_name",
            new_callable=AsyncMock,
            return_value=["rep", "sib"],
        ) as mock_expand:
            with patch("src.services.core.memory_store.db") as mock_db:
                mock_db.fetch = AsyncMock(return_value=[])
                await self.store.find_memories_by_entities(["rep"], "ct_1", limit=10)

        mock_expand.assert_awaited_once_with(["rep"], "ct_1")
        assert mock_db.fetch.call_args.args[1] == ["rep", "sib"]
        sql = mock_db.fetch.call_args.args[0]
        # 命中计数按"不同实体名"算：否则一个实体拆 3 行会被算成 3 次命中
        assert "COUNT(DISTINCT lower(btrim(e.name)))" in sql

    @pytest.mark.asyncio
    async def test_memory_lookup_single_row_when_flag_off(self, flag_off):
        with patch.object(
            self.store, "expand_entity_ids_by_name", new_callable=AsyncMock
        ) as mock_expand:
            with patch("src.services.core.memory_store.db") as mock_db:
                mock_db.fetch = AsyncMock(return_value=[])
                await self.store.find_memories_by_entities(["rep"], "ct_1", limit=10)

        mock_expand.assert_not_called()
        assert mock_db.fetch.call_args.args[1] == ["rep"]
        assert "COUNT(me.entity_id)" in mock_db.fetch.call_args.args[0]


class TestTraverseFamilyAware:
    def setup_method(self):
        self.store = MemoryStore()

    @pytest.mark.asyncio
    async def test_family_edges_are_unioned(self, flag_on):
        """遍历必须把家族内所有行的边并起来查（否则次行的边永远走不到）。"""
        neighbor_calls = []

        async def fake_neighbors(entity_ids, direction, relation_types=None, container_tag=None):
            neighbor_calls.append((list(entity_ids), direction))
            return []

        with patch.object(
            self.store,
            "resolve_entity_families",
            new_callable=AsyncMock,
            return_value={"rep": ["rep", "sib"]},
        ):
            with patch.object(
                self.store, "_entity_neighbor_ids", side_effect=fake_neighbors
            ):
                with patch("src.services.core.memory_store.db") as mock_db:
                    mock_db.fetchrow = AsyncMock(return_value=_entity_row("rep"))
                    results = await self.store.traverse_entity_relations(
                        "rep", max_depth=1, max_nodes=3, container_tag="ct_1"
                    )

        assert [e.id for e in results] == ["rep"]
        assert neighbor_calls[0][0] == ["rep", "sib"]  # 家族全体，不是单行
        assert neighbor_calls[0][1] == "out"
        assert neighbor_calls[1][1] == "in"

    @pytest.mark.asyncio
    async def test_single_row_when_flag_off(self, flag_off):
        neighbor_calls = []

        async def fake_neighbors(entity_ids, direction, relation_types=None, container_tag=None):
            neighbor_calls.append(list(entity_ids))
            return []

        with patch.object(
            self.store, "resolve_entity_families", new_callable=AsyncMock
        ) as mock_families:
            with patch.object(
                self.store, "_entity_neighbor_ids", side_effect=fake_neighbors
            ):
                with patch("src.services.core.memory_store.db") as mock_db:
                    mock_db.fetchrow = AsyncMock(return_value=_entity_row("rep"))
                    await self.store.traverse_entity_relations(
                        "rep", max_depth=1, max_nodes=3, container_tag="ct_1"
                    )

        mock_families.assert_not_called()
        assert neighbor_calls == [["rep"], ["rep"]]

    @pytest.mark.asyncio
    async def test_repeated_calls_are_identical(self, flag_on):
        """同一 query 两次跑必须完全一致（本次改动的验收标准）。"""

        async def fake_neighbors(entity_ids, direction, relation_types=None, container_tag=None):
            if direction == "out":
                return ["n2", "n1"]
            return ["n3"]

        async def fake_families(ids, container_tag=None):
            return {str(i): [str(i)] for i in ids}

        async def fake_fetchrow(sql, entity_id):
            return _entity_row(str(entity_id))

        seqs = []
        for _ in range(3):
            with patch.object(
                self.store, "resolve_entity_families", side_effect=fake_families
            ):
                with patch.object(
                    self.store, "_entity_neighbor_ids", side_effect=fake_neighbors
                ):
                    with patch("src.services.core.memory_store.db") as mock_db:
                        mock_db.fetchrow = AsyncMock(side_effect=fake_fetchrow)
                        results = await self.store.traverse_entity_relations(
                            "rep", max_depth=2, max_nodes=3, container_tag="ct_1"
                        )
            seqs.append([(e.id, e.name) for e in results])

        assert seqs[0] == seqs[1] == seqs[2]
        assert [s[0] for s in seqs[0]] == ["rep", "n2", "n1"]  # 跟随边查询的确定性顺序

    @pytest.mark.asyncio
    async def test_max_nodes_still_includes_start(self, flag_on):
        async def fake_neighbors(entity_ids, direction, relation_types=None, container_tag=None):
            return ["n1", "n2", "n3", "n4"] if direction == "out" else []

        async def fake_families(ids, container_tag=None):
            return {str(i): [str(i)] for i in ids}

        async def fake_fetchrow(sql, entity_id):
            return _entity_row(str(entity_id))

        with patch.object(self.store, "resolve_entity_families", side_effect=fake_families):
            with patch.object(
                self.store, "_entity_neighbor_ids", side_effect=fake_neighbors
            ):
                with patch("src.services.core.memory_store.db") as mock_db:
                    mock_db.fetchrow = AsyncMock(side_effect=fake_fetchrow)
                    results = await self.store.traverse_entity_relations(
                        "rep", max_depth=2, max_nodes=3, container_tag="ct_1"
                    )

        assert len(results) == 3
        assert results[0].id == "rep"
