"""crystal 单元测试：对账计分 / B5 初值 / 强度权重（无 DB / 无 key，test-strategy §1）"""

import pytest

from src.api.crystal.reconcile_service import (
    STRENGTH_WEIGHTS,
    b5_prior,
    content_confidence_from_prior,
    reinforce_score,
)
from src.api.crystal.recall_service import (
    CONTENT_UNKNOWN_FALLBACK,
    content_factor,
    final_score,
    _relevance_from_cosine,
)


class TestB5Priors:
    """B5 初值档位表（entity-attributes §7.4）逐格验证"""

    @pytest.mark.parametrize(
        "source_kind,claim_kind,expected",
        [
            ("agent_add", "fact", (4, 1)),
            ("agent_add", "preference", (5, 1)),
            ("agent_add", "constraint", (4, 1)),
            ("agent_add", "learned-pattern", (3, 1)),
            ("user_correction", "fact", (6, 1)),
            ("user_correction", "preference", (6, 1)),
            ("user_correction", "constraint", (6, 1)),
            ("user_correction", "learned-pattern", (6, 1)),
            ("outcome_trace", "fact", (3, 1)),
            ("document", "fact", (2, 1)),
        ],
    )
    def test_grid_values(self, source_kind, claim_kind, expected):
        assert b5_prior(source_kind, claim_kind) == expected

    def test_uncovered_combination_returns_none(self):
        assert b5_prior("bogus_kind", "fact") is None


class TestContentConfidenceFromPrior:
    """Beta 期望 α/(α+β) + inference 门控 ×0.7（§7.4 规则 2）"""

    def test_agent_fact(self):
        assert content_confidence_from_prior("agent_add", "fact", None) == 0.8

    def test_user_correction(self):
        assert content_confidence_from_prior("user_correction", "fact", None) == pytest.approx(6 / 7, abs=1e-3)

    def test_inference_discount(self):
        # agent_add/fact 初值 0.8 → inference 降档：α×0.7 → 2.8/(2.8+1) ≈ 0.7368
        conf = content_confidence_from_prior("agent_add", "fact", "inference")
        assert conf is not None
        assert conf < 0.8
        assert conf == pytest.approx(2.8 / 3.8, abs=1e-3)

    def test_verbatim_no_discount(self):
        conf_verbatim = content_confidence_from_prior("agent_add", "fact", "verbatim")
        conf_none = content_confidence_from_prior("agent_add", "fact", None)
        assert conf_verbatim == conf_none == 0.8

    def test_uncovered_returns_none(self):
        assert content_confidence_from_prior("bogus", "fact", None) is None


class TestReinforceScore:
    """reinforce 计分（§4.3 实现拍板：期望直接移动）"""

    def test_none_confidence_initializes_from_mass(self):
        assert reinforce_score(None, 0.8) == 0.8

    def test_zero_weight_no_change(self):
        assert reinforce_score(0.5, 0.0) == 0.5
        assert reinforce_score(0.5, STRENGTH_WEIGHTS["agent_inference"]) == 0.5

    def test_positive_weight_moves_up(self):
        result = reinforce_score(0.5, 0.5)
        assert result > 0.5

    def test_high_confidence_saturates(self):
        result = reinforce_score(0.99, 1.0)
        assert result <= 1.0

    def test_discount_applied(self):
        full = reinforce_score(0.5, 0.8)
        discounted = reinforce_score(0.5, 0.8, discount=0.7)
        assert discounted < full


class TestRecallScoring:
    """召回精排公式（recall-design §2）：final = relevance × content × reuse"""

    def test_relevance_mapping(self):
        assert _relevance_from_cosine(1.0) == 1.0
        assert _relevance_from_cosine(0.0) == 0.5
        assert _relevance_from_cosine(-1.0) == 0.0

    def test_content_factor_none_falls_back(self):
        assert content_factor(None) == CONTENT_UNKNOWN_FALLBACK
        assert content_factor(0.8) == 0.8

    def test_final_score(self):
        assert final_score(1.0, 0.8) == 0.8
        assert final_score(0.5, None) == pytest.approx(0.5 * 0.4, abs=1e-3)

    def test_reuse_is_identity_in_phase_one(self):
        assert final_score(1.0, 0.8, reuse=1.0) == 0.8


class TestDecomposeClaims:
    """M2.1 拆条（LLM ①）：粒度判据落地 + 降级路径（无 DB，mock LLM）"""

    @pytest.mark.anyio
    async def test_decompose_multi_claims(self, monkeypatch):
        """多独立结论 → 拆出 N 条原子 claim（含 event_key / evidence_quote）"""
        from src.api.crystal import reconcile_service

        async def fake_extract_json(prompt, temperature=0.0, max_tokens=3000):
            return {
                "claims": [
                    {"id": "c1", "statement": "项目部署选型倾向 Miniflux", "claim_kind": "fact",
                     "event_key": "e1", "evidence_quote": "部署选型偏 Miniflux", "relations": []},
                    {"id": "c2", "statement": "初期信息源数量上限为 20", "claim_kind": "constraint",
                     "event_key": "e1", "evidence_quote": "初期只加 ≤20 个信息源", "relations": []},
                ]
            }

        class _FakeLLM:
            async def aextract_json(self, prompt, temperature=0.0, max_tokens=3000):
                return await fake_extract_json(prompt, temperature, max_tokens)

        monkeypatch.setattr(reconcile_service, "get_llm_client", lambda: _FakeLLM())
        claims = await reconcile_service._llm_decompose_claims(
            {"content": "部署选型偏 Miniflux，初期只加 ≤20 个信息源", "source_kind": "agent_add"}
        )
        assert len(claims) == 2
        assert claims[0]["statement"] == "项目部署选型倾向 Miniflux"
        assert claims[0]["claim_kind"] == "fact"
        assert claims[0]["event_key"] == "e1"
        assert claims[0]["evidence_quote"] == "部署选型偏 Miniflux"
        assert claims[1]["claim_kind"] == "constraint"

    @pytest.mark.anyio
    async def test_decompose_llm_failure_no_fallback(self, monkeypatch):
        """LLM 失败 → 返回空（不降级原文——2026-08-19 用户拍板：拆条失败一律不自动降级，
        隔离到 workbench 等人工重试/裁决）"""
        from src.api.crystal import reconcile_service

        class _FakeLLM:
            async def aextract_json(self, prompt, temperature=0.0, max_tokens=3000):
                raise RuntimeError("LLM 挂了")

        monkeypatch.setattr(reconcile_service, "get_llm_client", lambda: _FakeLLM())
        claims = await reconcile_service._llm_decompose_claims(
            {"content": "张三喜欢喝咖啡", "source_kind": "agent_add"}
        )
        assert claims == []

    @pytest.mark.anyio
    async def test_decompose_caps_at_max(self, monkeypatch):
        """拆出条数不超过 MAX_CLAIMS_PER_EVIDENCE（防过度输出）"""
        from src.api.crystal import reconcile_service

        many_claims = [
            {"id": f"c{i}", "statement": f"断言{i}", "claim_kind": "fact",
             "event_key": "e1", "evidence_quote": None, "relations": []}
            for i in range(30)
        ]

        class _FakeLLM:
            async def aextract_json(self, prompt, temperature=0.0, max_tokens=3000):
                return {"claims": many_claims}

        monkeypatch.setattr(reconcile_service, "get_llm_client", lambda: _FakeLLM())
        claims = await reconcile_service._llm_decompose_claims(
            {"content": "长文本", "source_kind": "agent_add"}
        )
        assert len(claims) <= reconcile_service.MAX_CLAIMS_PER_EVIDENCE


class TestDoubleLimit:
    """M2.1 双上限常量（claim-atomicity §4.2）"""

    def test_thresholds(self):
        from src.api.crystal.reconcile_service import (
            MAX_EVIDENCE_CHARS,
            MAX_CLAIMS_PER_EVIDENCE,
        )

        assert MAX_EVIDENCE_CHARS == 1500
        assert MAX_CLAIMS_PER_EVIDENCE == 15

    def test_fallback_claim_kind(self):
        from src.api.crystal.reconcile_service import _fallback_claim_kind

        assert _fallback_claim_kind("必须遵守规范") == "constraint"
        assert _fallback_claim_kind("must use this") == "constraint"
        assert _fallback_claim_kind("项目用了 FastAPI") == "fact"
