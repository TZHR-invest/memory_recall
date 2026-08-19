"""
crystal 对账服务（写路径核心，reconciliation-design v1）

Evidence 落库后异步对账：embedding 步 → 候选定位（向量检索 active claim）→
碰撞判定（LLM 结构化 JSON，temperature=0；user_correction 特权跳过 LLM）→
单事务写 Claim + lineage_edge + claim_evidence + claim_activity + status 物化
+ content_confidence（reinforce 计分）→ 推进 evidence_processing 状态机。

关键不变量（entity-attributes §0 / reconciliation-design §2.2）：
- 对账产物单事务提交，失败回滚 → evidence_processing 保持可重试（幂等重放安全）
- 不变量①：新 claim 必带 ≥1 条 claim_evidence（同事务，应用层保证）
- 边不驻留触发证据，因果追溯写 claim_activity（同事务）
- reinforce 只追加证据关联 + 计分，不复制 claim 行
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from src.database import db
from src.embedding.client import get_embedding_client
from src.llm.client import get_llm_client
from src.logging_utils import generate_trace_id, get_trace_id, reset_trace_id, set_trace_id

logger = logging.getLogger(__name__)

# ---- 强度权重表（reconciliation-design §4.1） ----
STRENGTH_WEIGHTS = {
    "artifact_verified": 1.0,   # artifact 验证（测试/构建/退出码）
    "user_verbatim": 0.8,       # 用户另一场合 verbatim 明确陈述
    "user_paraphrase": 0.6,     # 用户 paraphrase
    "user_confirm": 0.5,        # 用户显式确认（workbench confirm）
    "agent_paraphrase": 0.3,    # agent 提炼 paraphrase（extraction_type=paraphrase）
    "agent_inference": 0.0,     # agent 推断 inference（不给分）
    "reuse_only": 0.0,          # 仅被召回/被使用（独立通道，永不喂 content）
}

# ---- 派生折扣分型（reconciliation-design §4.2） ----
DERIVATION_DISCOUNT = {
    "general": 0.7,   # 常规 claim→claim（generalizes/supersede 继承证据）
    "inference": 0.5,  # 决策/推断类派生
    "preference": 1.0,  # 偏好类派生（不折扣）
}

# ---- Alpha/Beta 上限（§4.3 工程 heuristic） ----
MAX_ALPHA_BETA = 100

# ---- B5 初值网格（entity-attributes §7.4） ----
# source_kind × claim_kind → (α, β)
B5_PRIORS: Dict[Tuple[str, str], Tuple[int, int]] = {
    ("agent_add", "fact"): (4, 1),
    ("agent_add", "preference"): (5, 1),
    ("agent_add", "constraint"): (4, 1),
    ("agent_add", "learned-pattern"): (3, 1),
    ("user_correction", "fact"): (6, 1),
    ("user_correction", "preference"): (6, 1),
    ("user_correction", "constraint"): (6, 1),
    ("user_correction", "learned-pattern"): (6, 1),
    ("outcome_trace", "fact"): (3, 1),
    ("outcome_trace", "preference"): (3, 1),
    ("outcome_trace", "constraint"): (3, 1),
    ("outcome_trace", "learned-pattern"): (3, 1),
    ("document", "fact"): (2, 1),
    ("document", "preference"): (2, 1),
    ("document", "constraint"): (2, 1),
    ("document", "learned-pattern"): (2, 1),
}

INFERENCE_DISCOUNT = 0.7  # extraction_type=inference 门控降档（§7.4 规则 2）

# ---- 碰撞判定结果 ----
JUDGMENT_CONFLICT = "CONFLICT"
JUDGMENT_REDUNDANT = "REDUNDANT"
JUDGMENT_SUPPORT = "SUPPORT"
JUDGMENT_UNRELATED = "UNRELATED"
JUDGMENTS = {JUDGMENT_CONFLICT, JUDGMENT_REDUNDANT, JUDGMENT_SUPPORT, JUDGMENT_UNRELATED}

CONFLICT_SUPERSEDE_THRESHOLD = 3  # 单条 evidence 触发 >3 条 supersede → 投毒信号

# ---- M2.1 双上限（claim-atomicity §4.2 / ADR-0020） ----
# evidence 字数上限：超限不自动拆条（默认隔离，留存 workbench 待裁决）
MAX_EVIDENCE_CHARS = 1500
# 拆出条目上限：单次拆条拆出超过此数 → 视为密度异常（workbench 人工审视）
MAX_CLAIMS_PER_EVIDENCE = 15


def b5_prior(source_kind: str, claim_kind: str) -> Optional[Tuple[int, int]]:
    """B5 初值网格（entity-attributes §7.4）；网格未覆盖 → None（UNKNOWN 不入表）"""
    return B5_PRIORS.get((source_kind, claim_kind))


def apply_extraction_discount(alpha: float, beta: float, extraction_type: Optional[str]) -> Tuple[float, float]:
    """extraction_type=inference 门控降档 ×0.7（§7.4 规则 2）"""
    if extraction_type == "inference":
        return alpha * INFERENCE_DISCOUNT, beta
    return alpha, beta


def content_confidence_from_prior(source_kind: str, claim_kind: str, extraction_type: Optional[str]) -> Optional[float]:
    """建 claim 时 content_confidence 初值 = Beta 期望 α/(α+β)；网格未覆盖 → NULL（UNKNOWN）"""
    prior = b5_prior(source_kind, claim_kind)
    if prior is None:
        return None
    alpha, beta = apply_extraction_discount(float(prior[0]), float(prior[1]), extraction_type)
    return round(alpha / (alpha + beta), 4)


def reinforce_score(
    current_confidence: Optional[float],
    weight: float,
    discount: float = 1.0,
) -> Optional[float]:
    """reinforce 计分（§4.3 实现拍板：期望直接移动，等价 α/β 但不改 schema）。

    content_confidence 物化 Beta 期望 α/(α+β)；α/β 不落库（避免 schema 加两列）。
    更新规则（工程近似，V2 Beta-Binomial 校准）：
      - 当前 NULL（UNKNOWN，无先验）→ 初值 = 强度×折扣（一次证据的期望）
      - 有值 → 按"新证据 mass 占比"向 1 移动：conf += (1 - conf) × mass，
        其中 mass = 强度×折扣 × 0.2（单条 reinforce 移动上限，防单证据虚高）
    """
    if weight <= 0:
        return current_confidence
    mass = weight * discount
    if current_confidence is None:
        return round(min(mass, 1.0), 4)
    # 向 1 移动，移动量受 mass 控制（0.2 上限：1.0 强度单次最多 +0.2）
    step = mass * 0.2
    new_conf = current_confidence + (1.0 - current_confidence) * step
    return round(new_conf, 4)


def _strength_for_evidence(evidence: Dict[str, Any]) -> float:
    """按 evidence 属性定强度档（§4.1）。

    判定顺序（从强到弱）：
    - user_correction → 不参与计分（走特权 supersede），返回 0
    - extraction_type=verbatim + source_kind=agent_add → 用户 verbatim（0.8）
      （agent_add 是显式自报，视为"用户明确陈述"）
    - extraction_type=paraphrase → agent 提炼 paraphrase（0.3）
    - extraction_type=inference → agent 推断（0）
    - 默认 0.6（用户 paraphrase 兜底）
    """
    if evidence.get("source_kind") == "user_correction":
        return 0.0
    extraction_type = evidence.get("extraction_type")
    if extraction_type == "inference":
        return STRENGTH_WEIGHTS["agent_inference"]
    if extraction_type == "paraphrase":
        return STRENGTH_WEIGHTS["agent_paraphrase"]
    if extraction_type == "verbatim":
        return STRENGTH_WEIGHTS["user_verbatim"]
    # 无 extraction_type：agent_add 默认按用户 paraphrase（0.6）
    return STRENGTH_WEIGHTS["user_paraphrase"]


async def _embed(text: str) -> Optional[List[float]]:
    """生成向量（失败返回 None，对账 embedding 步失败 → evidence_processing failed 可重试）"""
    try:
        client = get_embedding_client()
        return await client.embed(text)
    except Exception as e:
        logger.error(f"crystal embedding 失败: {e}")
        return None


async def _llm_collision_judge(
    evidence: Dict[str, Any],
    candidates: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """LLM 碰撞判定（一次调用，temperature=0，结构化 JSON）。

    返回 [{claim_id, judgment, reason}]；LLM 失败/超时 → 全部 UNRELATED 降级（建新 claim），
    不阻塞对账（对账可靠性优先，v1 #17）。
    """
    if not candidates:
        return []
    try:
        llm = get_llm_client()
        candidate_texts = "\n".join(
            f"- claim_id: {c['id']}\n  statement: {c['statement']}"
            for c in candidates
        )
        prompt = f"""你是一个记忆对账助手。判断新证据与已有主张（claim）的关系。

新证据（Evidence）:
{evidence['content']}

已有 Claim 候选:
{candidate_texts}

对每个候选 claim 判断关系，只输出 JSON：
{{
  "relations": [
    {{"claim_id": "<候选id>", "judgment": "CONFLICT|REDUNDANT|SUPPORT|UNRELATED", "reason": "<一句话原因>"}}
  ]
}}

判定标准：
- CONFLICT: 新证据与 claim 矛盾（同一主题、结论相反/互斥）
- REDUNDANT: 新证据是 claim 的近似重复/同源复述（意思几乎一样）
- SUPPORT: 新证据支持/补充/佐证 claim（不矛盾、不重复、相关）
- UNRELATED: 无关
不要编造 claim_id，只对上面列出的候选判断。"""
        result = await llm.aextract_json(prompt, temperature=0.0, max_tokens=16000)
        if not result or "relations" not in result:
            logger.warning("crystal 碰撞判定 LLM 返回空，降级为 UNRELATED")
            return []
        relations = []
        for rel in result["relations"]:
            claim_id = rel.get("claim_id")
            judgment = rel.get("judgment")
            if claim_id and judgment in JUDGMENTS:
                relations.append(
                    {
                        "claim_id": claim_id,
                        "judgment": judgment,
                        "reason": rel.get("reason", ""),
                    }
                )
        return relations
    except Exception as e:
        logger.error(f"crystal 碰撞判定 LLM 失败: {e}，降级为 UNRELATED")
        return []


async def _llm_collision_judge_batch(
    evidence: Dict[str, Any],
    claims: List[Dict[str, Any]],
    candidates_by_claim: Dict[str, List[Dict[str, Any]]],
) -> List[Dict[str, Any]]:
    """LLM ② 碰撞判定批处理（M2.1，reconciliation-design §2.4）。

    一次调用把 N 条新 claim（拆条产物）连同各自检索到的候选一起判断：
    输出 [{claim_id, judgment, target_claim_id, reason}]（按新 claim 索引）。

    与 v1 单条 _llm_collision_judge 的区别：输入是新 claim（而非整条 evidence），
    每条新 claim 只对其检索到的候选判断（不互相干扰）；批处理省成本（N 条一次调用）。

    LLM 失败/超时 → 全部 UNRELATED 降级（建新 claim，不阻塞对账，v1 #17）。
    """
    if not claims:
        return []
    try:
        llm = get_llm_client()
        claim_blocks = []
        for i, c in enumerate(claims):
            cid = f"c{i + 1}"  # 临时 id，与 candidates_by_claim / 批量写对齐
            cands = candidates_by_claim.get(cid, [])
            cand_texts = "\n".join(
                f"- claim_id: {x['id']}\n  statement: {x['statement']}"
                for x in cands
            )
            claim_blocks.append(
                f"[新 Claim {cid}] {c['statement']}\n"
                f"  已有候选:\n{cand_texts if cand_texts else '  (无候选)'}"
            )
        prompt = f"""你是一个记忆对账助手。判断若干条新主张（Claim）与已有主张候选的关系。

新 Claim 列表（每条含其检索到的已有候选）:
{chr(10).join(claim_blocks)}

对每条新 Claim，对其列出的候选判断关系（CONFLICT/REDUNDANT/SUPPORT/UNRELATED）。
只输出 JSON:
{{
  "judgments": [
    {{"claim_id": "<新claim id>", "judgment": "CONFLICT|REDUNDANT|SUPPORT|UNRELATED", "target_claim_id": "<候选id，UNRELATED 可为空>", "reason": "<一句话原因>"}}
  ]
}}

判定标准：
- CONFLICT: 新 claim 与候选矛盾（同一主题、结论相反/互斥）
- REDUNDANT: 新 claim 是候选的近似重复/同源复述（意思几乎一样）
- SUPPORT: 新 claim 支持/补充/佐证候选（不矛盾、不重复、相关）
- UNRELATED: 无关（此时 target_claim_id 留空）
不要编造候选 id，只对每条新 claim 列出的候选判断。每条新 claim 最多一条 CONFLICT/REDUNDANT/SUPPORT（取最强），其余候选 UNRELATED。"""
        result = await llm.aextract_json(prompt, temperature=0.0, max_tokens=16000)
        if not result or "judgments" not in result:
            logger.warning("crystal 碰撞判定批处理 LLM 返回空，降级为 UNRELATED")
            return []
        judgments = []
        for j in result["judgments"]:
            claim_id = j.get("claim_id")
            judgment = j.get("judgment")
            if claim_id and judgment in JUDGMENTS:
                judgments.append(
                    {
                        "claim_id": claim_id,
                        "judgment": judgment,
                        "target_claim_id": j.get("target_claim_id") or None,
                        "reason": j.get("reason", ""),
                    }
                )
        return judgments
    except Exception as e:
        logger.error(f"crystal 碰撞判定批处理 LLM 失败: {e}，降级为 UNRELATED")
        return []


async def _llm_decompose_claims(
    evidence: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """LLM ① 拆条（M2.1，reconciliation-design §2.4 / claim-atomicity §3）。

    把 evidence 拆成 N 条原子 claim，输出 claims[] {statement, claim_kind,
    event_key, evidence_quote, relations}。

    策略：
    - 一律整段单次调用拆条（含长文本；重试 3 次兜底服务端间歇空响应）；
    - 拆条阶段**不含冲突/支持字段**（LLM 没看到存量结论，不猜冲突）。

    降级（不阻塞对账，v1 #17）：
    - 短文本（<500 字）拆条失败 → 降级为整条原文单 claim（短文本原文≈结论，可接受）；
    - 长文本（≥500 字）拆条失败 → 返回 []（不把原文照抄进 claim——那是"分层错误"重演），
      由上层 reconcile_evidence 判定为隔离/待人工裁决。

    （2026-08-19 修正：曾用"分块拆条"，实测分块碎片失去上下文（孤立列表项/标题）后
    模型拆条失败率更高——"拆分≠切句子，碎片不自足"（Claude round-01 自足性测试）。
    改为整段调用 + 重试，长文本失败走隔离。）
    """
    content = evidence.get("content", "")
    source_kind = evidence.get("source_kind", "agent_add")

    try:
        return await _decompose_single_call(evidence, source_kind)
    except Exception as e:
        # 2026-08-19 用户拍板：拆条失败一律不自动降级（不把原文照抄进 claim——
        # 那是"分层错误"重演）。返回空 → 上层 reconcile_evidence 隔离到 workbench
        # 待人工重试/裁决（evidence 保留，evidence_processing 标记 isolated）。
        logger.warning(f"crystal 拆条失败（{len(content)} 字）: {e}，返回空（隔离待人工裁决）")
        return []


async def _decompose_single_call(evidence: Dict[str, Any], source_kind: str) -> List[Dict[str, Any]]:
    """单次拆条 LLM 调用（短文本或单块）。失败自动重试 2 次（deepseek-v4-flash
    对复杂 JSON 输出存在间歇性空响应，实测时好时坏，重试提高成功率）。
    重试仍失败抛异常，由上层降级/隔离。"""
    content = evidence.get("content", "")
    last_error: Optional[Exception] = None
    for attempt in range(3):  # 首次 + 2 次重试
        try:
            claims = await _decompose_single_call_once(evidence, source_kind)
            if claims:
                return claims
            last_error = ValueError("拆条 LLM 返回空 claims")
        except Exception as e:
            last_error = e
        logger.warning(f"crystal 拆条第 {attempt + 1} 次失败: {last_error}，重试中...")
        await asyncio.sleep(0.5 * (attempt + 1))  # 0.5s / 1s 退避
    raise last_error if last_error else ValueError("拆条失败")


async def _decompose_single_call_once(evidence: Dict[str, Any], source_kind: str) -> List[Dict[str, Any]]:
    """单次拆条 LLM 调用（不重试）。失败抛异常由 _decompose_single_call 重试。"""
    content = evidence.get("content", "")
    llm = get_llm_client()
    prompt = f"""把下面这段内容拆分为原子主张（Claim）。每条约 15-80 字，独立可证伪。

内容:
{content}

规则（精简版）：
1. 粒度 = 独立生命周期：两个信息未来可能一个被改/失效、另一个仍成立 → 必须拆成两条。
2. 不要机械拆分必要上下文（时间/范围/条件/原因）：如"第一阶段上限 20 个"是一条，不拆成两条。
3. statement 脱离原文要能读懂（不要用"这个/那个"）；也不要整段复制原文。
4. claim_kind 四选一：fact / preference / constraint / learned-pattern（踩坑经验保留"条件-做法-结果"）。
5. event_key：同一段内容里一起说的多件事用同组 e1/e2。
6. evidence_quote（可选）：从原文逐字复制支撑该条的原文子句；复制不了就留空字符串。

只输出 JSON（不要输出其他内容）:
{{"claims": [{{"id": "c1", "statement": "<断言>", "claim_kind": "<四选一>", "event_key": "e1", "evidence_quote": "<原文子句或空>"}}]}}"""
    result = await llm.aextract_json(prompt, temperature=0.0, max_tokens=16000)
    if not result or "claims" not in result:
        raise ValueError("拆条 LLM 返回空")
    claims = []
    for c in result["claims"][:MAX_CLAIMS_PER_EVIDENCE]:
        statement = (c.get("statement") or "").strip()
        kind = c.get("claim_kind")
        if not statement:
            continue
        if kind not in {"fact", "preference", "constraint", "learned-pattern"}:
            kind = _fallback_claim_kind(content)
        claims.append(
            {
                "statement": statement,
                "claim_kind": kind,
                "event_key": c.get("event_key") or "e1",
                "evidence_quote": (c.get("evidence_quote") or "").strip() or None,
                "relations": [],
            }
        )
    if not claims:
        raise ValueError("拆条 LLM 输出空 claims")
    return claims


def _fallback_claim_kind(content: str) -> str:
    """拆条/提炼失败降级：关键词规则（constraint → constraint，否则 fact）。"""
    lowered = content.lower()
    if any(kw in lowered for kw in ["必须", "禁止", "不要", "always", "never", "required", "must"]):
        return "constraint"
    return "fact"


async def _llm_claim_kind_and_statement(
    content: str,
    source_kind: str,
    old_claim_kind: Optional[str] = None,
) -> Tuple[str, str]:
    """claim_kind 判定 + statement 提炼（对账 §2.3：规则优先，LLM 兜底）。

    - user_correction + 有旧 claim → 沿用旧 claim_kind（特权路径不走 LLM，§3.1）
    - 其余：LLM 一次判定；失败降级规则（constraint 关键词 → constraint，否则 fact）
    """
    if source_kind == "user_correction" and old_claim_kind:
        return old_claim_kind, content
    try:
        llm = get_llm_client()
        prompt = f"""判断下面这条观察属于哪类主张（claim_kind），并提炼为简洁断言（statement）。

观察: {content}

claim_kind 四选一：
- fact: 事实类断言
- preference: 主观喜好/习惯/语言风格/工作方式
- constraint: 项目/任务硬性边界、必须遵守的规则
- learned-pattern: 实践中验证有效的做法/技术决策/踩坑教训

只输出 JSON:
{{"claim_kind": "<四选一>", "statement": "<简洁断言，适用条件折入句子>"}}"""
        result = await llm.aextract_json(prompt, temperature=0.0, max_tokens=16000)
        if result and result.get("claim_kind") in {"fact", "preference", "constraint", "learned-pattern"}:
            statement = (result.get("statement") or content).strip()
            return result["claim_kind"], statement
    except Exception as e:
        logger.error(f"crystal claim_kind 判定 LLM 失败: {e}")
    # 降级规则
    lowered = content.lower()
    if any(kw in lowered for kw in ["必须", "禁止", "不要", "always", "never", "required", "must"]):
        return "constraint", content
    return "fact", content


def _embedding_to_str(embedding: Optional[List[float]]) -> Optional[str]:
    """pgvector 传参格式（v5 memory_store._embedding_to_str 同款）："[1.0,2.0,...]" """
    if not embedding:
        return None
    return "[" + ",".join(str(x) for x in embedding) + "]"


async def _find_candidate_claims(
    owner_type: str,
    owner_id: str,
    scope: Optional[str],
    embedding: Optional[List[float]],
    top_k: int = 20,
) -> List[Dict[str, Any]]:
    """候选定位（§2.3 ①）：向量检索同 owner active claim top-K + 同 scope 兜底。

    scope 语义与召回预过滤一致（recall-design §1）：请求 scope 时匹配
    claim.scope == scope 或 claim.scope IS NULL（全局知识）；请求 scope=NULL 时只匹配全局。
    """
    if not embedding:
        return []
    # scope 语义与召回预过滤一致：请求 scope 时匹配 claim.scope==scope 或全局（NULL）；
    # 请求 scope=NULL 时只匹配全局。动态参数避免 PG 无法推断类型。
    if scope is not None:
        scope_clause = "AND (scope = $3::text OR scope IS NULL)"
        params: List[Any] = [owner_type, owner_id, scope]
    else:
        scope_clause = "AND scope IS NULL"
        params = [owner_type, owner_id]
    async with db.get_connection() as conn:
        rows = await conn.fetch(
            f"""SELECT id, statement, claim_kind, content_confidence, scope
               FROM crystal.claim
               WHERE owner_type=$1 AND owner_id=$2 AND status='active'
                 AND embedding IS NOT NULL
                 {scope_clause}
               ORDER BY 1 - (embedding <=> ${len(params) + 1}::vector) ASC
               LIMIT ${len(params) + 2}""",
            *params,
            _embedding_to_str(embedding),
            top_k,
        )
        return [dict(r) for r in rows]


async def _write_reconcile_transaction(
    evidence: Dict[str, Any],
    relations: List[Dict[str, Any]],
    new_claim: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """对账单事务写入（§2.2 事务边界）。

    evidence: 已落库的 evidence 行（含 id, content, source_kind, scope, owner_type,
              owner_id, extraction_type, observed_at）
    relations: 碰撞判定结果（已过滤 UNRELATED）
    new_claim: 需新建的 claim 候选 {statement, claim_kind}（无则 None）

    返回 {created_claim_id, superseded_ids, reinforced_claim_id, poison_warning}
    """
    superseded_ids: List[str] = []
    reinforced_claim_id: Optional[str] = None
    created_claim_id: Optional[str] = None
    poison_warning = False

    async with db.get_connection() as conn:
        async with conn.transaction():
            # 1. 冲突路径（§3.2）：逐条 supersede
            conflicts = [r for r in relations if r["judgment"] == JUDGMENT_CONFLICT]
            if len(conflicts) > CONFLICT_SUPERSEDE_THRESHOLD:
                poison_warning = True
                logger.warning(
                    f"crystal 投毒信号: evidence {evidence['id']} 触发 {len(conflicts)} 条 supersede"
                )

            if conflicts:
                # 新建取代 claim（statement 从 E 提炼，claim_kind 判定）
                kind, statement = await _llm_claim_kind_and_statement(
                    evidence["content"], evidence["source_kind"]
                )
                confidence = content_confidence_from_prior(
                    evidence["source_kind"], kind, evidence.get("extraction_type")
                )
                new_claim_id = await conn.fetchval(
                    """INSERT INTO crystal.claim
                       (statement, claim_kind, content_confidence, scope, owner_type, owner_id,
                        status, embedding, created_at)
                       VALUES ($1, $2, $3, $4, $5, $6, 'active', $7, NOW())
                       RETURNING id""",
                    statement,
                    kind,
                    confidence,
                    evidence.get("scope"),
                    evidence["owner_type"],
                    evidence["owner_id"],
                    _embedding_to_str(evidence.get("embedding")),
                )
                created_claim_id = new_claim_id

                for rel in conflicts:
                    old_id = rel["claim_id"]
                    # edge: old --supersedes--> new
                    await conn.execute(
                        """INSERT INTO crystal.lineage_edge
                           (from_claim_id, to_claim_id, edge_type, reason, created_at)
                           VALUES ($1, $2, 'supersedes', $3, NOW())""",
                        old_id,
                        new_claim_id,
                        f"新证据冲突: {rel.get('reason', '')}",
                    )
                    # status 物化（同事务）
                    await conn.execute(
                        "UPDATE crystal.claim SET status='superseded' WHERE id=$1",
                        old_id,
                    )
                    # claim_activity（审计，同事务）
                    await conn.execute(
                        """INSERT INTO crystal.claim_activity
                           (claim_id, action, actor_type, actor_id, triggered_by_evidence_id,
                            detail, created_at)
                           VALUES ($1, 'superseded_by', 'system', NULL, $2, $3, NOW())""",
                        old_id,
                        evidence["id"],
                        json.dumps({"new_claim_id": new_claim_id, "reason": rel.get("reason", "")}),
                    )
                    superseded_ids.append(old_id)

                # claim_evidence: new ← E
                await conn.execute(
                    """INSERT INTO crystal.claim_evidence (claim_id, evidence_id, role, created_at)
                       VALUES ($1, $2, 'support', NOW())""",
                    new_claim_id,
                    evidence["id"],
                )

                # 投毒告警日志（§6）
                if poison_warning:
                    await conn.execute(
                        """INSERT INTO crystal.claim_activity
                           (claim_id, action, actor_type, actor_id, triggered_by_evidence_id,
                            detail, created_at)
                           VALUES ($1, 'poison_warning', 'system', NULL, $2, $3, NOW())""",
                        new_claim_id,
                        evidence["id"],
                        json.dumps({"superseded_count": len(conflicts)}),
                    )
            elif new_claim:
                # 2. 无冲突无候选 → 建新 claim（§2.3）
                kind = new_claim["claim_kind"]
                statement = new_claim["statement"]
                confidence = content_confidence_from_prior(
                    evidence["source_kind"], kind, evidence.get("extraction_type")
                )
                new_claim_id = await conn.fetchval(
                    """INSERT INTO crystal.claim
                       (statement, claim_kind, content_confidence, scope, owner_type, owner_id,
                        status, embedding, created_at)
                       VALUES ($1, $2, $3, $4, $5, $6, 'active', $7, NOW())
                       RETURNING id""",
                    statement,
                    kind,
                    confidence,
                    evidence.get("scope"),
                    evidence["owner_type"],
                    evidence["owner_id"],
                    _embedding_to_str(evidence.get("embedding")),
                )
                created_claim_id = new_claim_id
                # 不变量①：新 claim 必带 claim_evidence
                await conn.execute(
                    """INSERT INTO crystal.claim_evidence (claim_id, evidence_id, role, created_at)
                       VALUES ($1, $2, 'support', NOW())""",
                    new_claim_id,
                    evidence["id"],
                )
                # claim_activity: claim 创建审计
                await conn.execute(
                    """INSERT INTO crystal.claim_activity
                       (claim_id, action, actor_type, actor_id, triggered_by_evidence_id,
                        detail, created_at)
                       VALUES ($1, 'confirmed', 'system', NULL, $2, $3, NOW())""",
                    new_claim_id,
                    evidence["id"],
                    json.dumps({"created_from_evidence": True}),
                )
            else:
                # 3. reinforce 路径（§3.3）：冗余/支持 → 追加关联 + 计分
                reinforces = [r for r in relations if r["judgment"] in (JUDGMENT_REDUNDANT, JUDGMENT_SUPPORT)]
                if reinforces:
                    # 取最强的一条 reinforce 目标（同源复述闸门在计分时判断）
                    target = reinforces[0]
                    reinforced_claim_id = target["claim_id"]

                    # 追加 claim_evidence（不复制 claim 行，§3.3）
                    await conn.execute(
                        """INSERT INTO crystal.claim_evidence (claim_id, evidence_id, role, created_at)
                           VALUES ($1, $2, 'support', NOW())
                           ON CONFLICT (claim_id, evidence_id) DO NOTHING""",
                        reinforced_claim_id,
                        evidence["id"],
                    )
                    # reinforce 计分（§4）：强度 × 折扣；同源复述闸门
                    strength = _strength_for_evidence(evidence)
                    # 同源闸门：E 与目标 claim 既有证据同源（source_ref 同一 session）→ 不计分
                    same_source = await _is_same_source(conn, reinforced_claim_id, evidence)
                    if strength > 0 and not same_source:
                        current_conf = await conn.fetchval(
                            "SELECT content_confidence FROM crystal.claim WHERE id=$1",
                            reinforced_claim_id,
                        )
                        new_conf = reinforce_score(current_conf, strength)
                        await conn.execute(
                            "UPDATE crystal.claim SET content_confidence=$1 WHERE id=$2",
                            new_conf,
                            reinforced_claim_id,
                        )
                    # claim_activity: reinforce 审计
                    await conn.execute(
                        """INSERT INTO crystal.claim_activity
                           (claim_id, action, actor_type, actor_id, triggered_by_evidence_id,
                            detail, created_at)
                           VALUES ($1, 'confirmed', 'system', NULL, $2, $3, NOW())""",
                        reinforced_claim_id,
                        evidence["id"],
                        json.dumps({"action": "reinforce", "strength": strength, "scored": strength > 0 and not same_source}),
                    )

    return {
        "created_claim_id": created_claim_id,
        "superseded_ids": superseded_ids,
        "reinforced_claim_id": reinforced_claim_id,
        "poison_warning": poison_warning,
    }


async def _write_reconcile_transaction_batch(
    evidence: Dict[str, Any],
    claims: List[Dict[str, Any]],
    judgments: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """对账单事务批量写（M2.1，reconciliation-design §2.4）。

    把拆条产出的 N 条新 claim 连同碰撞判定结果（LLM ② 批处理输出）单事务写入：
    - 每条新 claim: INSERT claim（含 event_key）+ claim_evidence（含 quoted_text）+ claim_activity
    - CONFLICT → supersede 边（旧 claim → 新 claim）+ 旧 status=superseded
    - REDUNDANT/SUPPORT → reinforce 目标 claim（追加证据 + 计分）
    - UNRELATED / 无候选 → 新 claim 直接入库

    evidence: 已落库 evidence 行
    claims: 拆条产物 [{statement, claim_kind, event_key, evidence_quote, relations}]
    judgments: LLM ② 输出 [{claim_id, judgment, target_claim_id, reason}]
    （claim_id 对应 claims 的顺序 id: c1, c2, ...——调用方负责对齐）

    返回 {created_claim_ids, superseded_ids, reinforced_claim_ids, poison_warning}
    """
    created_claim_ids: List[str] = []
    superseded_ids: List[str] = []
    reinforced_claim_ids: List[str] = []
    poison_warning = False

    # 为每条新 claim 建临时 id（事务内用），LLM ② 输出按此对齐
    claim_ids = [f"c{i + 1}" for i in range(len(claims))]
    judgment_by_claim: Dict[str, List[Dict[str, Any]]] = {cid: [] for cid in claim_ids}
    for j in judgments:
        if j.get("claim_id") in judgment_by_claim:
            judgment_by_claim[j["claim_id"]].append(j)

    conflicts_total = 0

    async with db.get_connection() as conn:
        async with conn.transaction():
            for idx, claim in enumerate(claims):
                cid = claim_ids[idx]
                statement = claim["statement"]
                kind = claim["claim_kind"]
                event_key = claim.get("event_key")
                quote = claim.get("evidence_quote")
                # 该新 claim 的判定（取第一条非 UNRELATED，按序）
                rels = judgment_by_claim.get(cid, [])
                conflict = next((r for r in rels if r["judgment"] == JUDGMENT_CONFLICT), None)
                reinforce = next(
                    (r for r in rels if r["judgment"] in (JUDGMENT_REDUNDANT, JUDGMENT_SUPPORT)),
                    None,
                )

                if reinforce and reinforce.get("target_claim_id"):
                    # reinforce 路径：追加证据关联 + 计分（不建新 claim）
                    target_id = reinforce["target_claim_id"]
                    reinforced_claim_ids.append(target_id)
                    await conn.execute(
                        """INSERT INTO crystal.claim_evidence (claim_id, evidence_id, role, quoted_text, created_at)
                           VALUES ($1, $2, 'support', $3, NOW())
                           ON CONFLICT (claim_id, evidence_id) DO NOTHING""",
                        target_id,
                        evidence["id"],
                        quote,
                    )
                    strength = _strength_for_evidence(evidence)
                    same_source = await _is_same_source(conn, target_id, evidence)
                    if strength > 0 and not same_source:
                        current_conf = await conn.fetchval(
                            "SELECT content_confidence FROM crystal.claim WHERE id=$1",
                            target_id,
                        )
                        new_conf = reinforce_score(current_conf, strength)
                        await conn.execute(
                            "UPDATE crystal.claim SET content_confidence=$1 WHERE id=$2",
                            new_conf,
                            target_id,
                        )
                    await conn.execute(
                        """INSERT INTO crystal.claim_activity
                           (claim_id, action, actor_type, actor_id, triggered_by_evidence_id,
                            detail, created_at)
                           VALUES ($1, 'confirmed', 'system', NULL, $2, $3, NOW())""",
                        target_id,
                        evidence["id"],
                        json.dumps({"action": "reinforce", "strength": strength, "scored": strength > 0 and not same_source}),
                    )
                    continue

                # 新建 claim（UNRELATED / 无候选 / 冲突路径的新取代 claim）
                confidence = content_confidence_from_prior(
                    evidence["source_kind"], kind, evidence.get("extraction_type")
                )
                new_claim_id = await conn.fetchval(
                    """INSERT INTO crystal.claim
                       (statement, claim_kind, content_confidence, scope, owner_type, owner_id,
                        status, event_key, embedding, created_at)
                       VALUES ($1, $2, $3, $4, $5, $6, 'active', $7, $8, NOW())
                       RETURNING id""",
                    statement,
                    kind,
                    confidence,
                    evidence.get("scope"),
                    evidence["owner_type"],
                    evidence["owner_id"],
                    event_key,
                    _embedding_to_str(evidence.get("embedding")),
                )
                created_claim_ids.append(new_claim_id)

                # claim_evidence（不变量①）
                await conn.execute(
                    """INSERT INTO crystal.claim_evidence (claim_id, evidence_id, role, quoted_text, created_at)
                       VALUES ($1, $2, 'support', $3, NOW())""",
                    new_claim_id,
                    evidence["id"],
                    quote,
                )
                # claim_activity: 创建审计
                await conn.execute(
                    """INSERT INTO crystal.claim_activity
                       (claim_id, action, actor_type, actor_id, triggered_by_evidence_id,
                        detail, created_at)
                       VALUES ($1, 'confirmed', 'system', NULL, $2, $3, NOW())""",
                    new_claim_id,
                    evidence["id"],
                    json.dumps({"created_from_evidence": True, "event_key": event_key}),
                )

                # 冲突路径：旧 claim --supersedes--> 新 claim
                if conflict and conflict.get("target_claim_id"):
                    old_id = conflict["target_claim_id"]
                    conflicts_total += 1
                    await conn.execute(
                        """INSERT INTO crystal.lineage_edge
                           (from_claim_id, to_claim_id, edge_type, reason, created_at)
                           VALUES ($1, $2, 'supersedes', $3, NOW())""",
                        old_id,
                        new_claim_id,
                        f"新证据冲突: {conflict.get('reason', '')}",
                    )
                    await conn.execute(
                        "UPDATE crystal.claim SET status='superseded' WHERE id=$1",
                        old_id,
                    )
                    await conn.execute(
                        """INSERT INTO crystal.claim_activity
                           (claim_id, action, actor_type, actor_id, triggered_by_evidence_id,
                            detail, created_at)
                           VALUES ($1, 'superseded_by', 'system', NULL, $2, $3, NOW())""",
                        old_id,
                        evidence["id"],
                        json.dumps({"new_claim_id": new_claim_id, "reason": conflict.get("reason", "")}),
                    )
                    superseded_ids.append(old_id)

            # 投毒信号（§6）：单条 evidence 触发 >3 条 supersede
            if conflicts_total > CONFLICT_SUPERSEDE_THRESHOLD:
                poison_warning = True
                logger.warning(
                    f"crystal 投毒信号: evidence {evidence['id']} 触发 {conflicts_total} 条 supersede"
                )
                if created_claim_ids:
                    await conn.execute(
                        """INSERT INTO crystal.claim_activity
                           (claim_id, action, actor_type, actor_id, triggered_by_evidence_id,
                            detail, created_at)
                           VALUES ($1, 'poison_warning', 'system', NULL, $2, $3, NOW())""",
                        created_claim_ids[0],
                        evidence["id"],
                        json.dumps({"superseded_count": conflicts_total}),
                    )

    return {
        "created_claim_ids": created_claim_ids,
        "superseded_ids": superseded_ids,
        "reinforced_claim_ids": reinforced_claim_ids,
        "poison_warning": poison_warning,
    }


async def _is_same_source(conn, claim_id: str, evidence: Dict[str, Any]) -> bool:
    """同源复述闸门（§3.3）：E 与 claim 既有证据同源（source_ref 同一 session）→ True 不计分。"""
    source_ref = evidence.get("source_ref")
    session_id = source_ref.get("session_id") if isinstance(source_ref, dict) else None
    if not session_id:
        return False
    rows = await conn.fetch(
        """SELECT ce.evidence_id FROM crystal.claim_evidence ce
           JOIN crystal.evidence e ON e.id = ce.evidence_id
           WHERE ce.claim_id=$1 AND e.source_ref->>'session_id'=$2
           LIMIT 1""",
        claim_id,
        session_id,
    )
    return len(rows) > 0


async def reconcile_correction(
    target_claim_id: str,
    new_statement: str,
    owner_type: str,
    owner_id: str,
    source_ref: Optional[Dict[str, Any]] = None,
    actor_id: Optional[str] = None,
    reason: str = "用户纠正",
) -> Dict[str, Any]:
    """用户纠正特权 supersede（reconciliation-design §3.1，US-R3 / A3）。

    workbench correct 调用：创建 user_correction Evidence → 单事务 supersede 指认 claim。
    不走 LLM 碰撞（特权路径）；claim_kind 沿用旧 claim。
    """
    # 1. 建 user_correction Evidence（不可再生地基完整，v1 #4）
    async with db.get_connection() as conn:
        # 校验目标 claim 归属
        target = await conn.fetchrow(
            """SELECT id, claim_kind, scope, owner_type, owner_id
               FROM crystal.claim
               WHERE id=$1 AND owner_type=$2 AND owner_id=$3""",
            target_claim_id,
            owner_type,
            owner_id,
        )
        if not target:
            raise ValueError(f"Claim '{target_claim_id}' not found or not owned by you")

        correction_evidence_id = await conn.fetchval(
            """INSERT INTO crystal.evidence
               (observed_at, source_kind, content, scope, owner_type, owner_id,
                source_ref, extraction_type, created_at)
               VALUES (NOW(), 'user_correction', $1, $2, $3, $4, $5, 'verbatim', NOW())
               RETURNING id""",
            new_statement,
            target["scope"],
            owner_type,
            owner_id,
            json.dumps(source_ref) if source_ref else None,
        )

        # 2. 单事务 supersede
        async with conn.transaction():
            # 新 claim：statement=new_statement，claim_kind 沿用旧 claim（§3.1）
            confidence = content_confidence_from_prior("user_correction", target["claim_kind"], "verbatim")
            new_claim_id = await conn.fetchval(
                """INSERT INTO crystal.claim
                   (statement, claim_kind, content_confidence, scope, owner_type, owner_id,
                    status, created_at)
                   VALUES ($1, $2, $3, $4, $5, $6, 'active', NOW())
                   RETURNING id""",
                new_statement,
                target["claim_kind"],
                confidence,
                target["scope"],
                owner_type,
                owner_id,
            )
            # edge: old --supersedes(reason="用户纠正")--> new
            await conn.execute(
                """INSERT INTO crystal.lineage_edge
                   (from_claim_id, to_claim_id, edge_type, reason, created_at)
                   VALUES ($1, $2, 'supersedes', $3, NOW())""",
                target_claim_id,
                new_claim_id,
                reason,
            )
            # claim_evidence: new ← correction_ev（不传递旧证据，§3.1）
            await conn.execute(
                """INSERT INTO crystal.claim_evidence (claim_id, evidence_id, role, created_at)
                   VALUES ($1, $2, 'support', NOW())""",
                new_claim_id,
                correction_evidence_id,
            )
            # claim_activity: 审计
            await conn.execute(
                """INSERT INTO crystal.claim_activity
                   (claim_id, action, actor_type, actor_id, triggered_by_evidence_id,
                    detail, created_at)
                   VALUES ($1, 'superseded_by', 'user', $2, $3, $4, NOW())""",
                target_claim_id,
                actor_id,
                correction_evidence_id,
                json.dumps({"new_claim_id": new_claim_id, "reason": reason}),
            )
            # status 物化：old→superseded, new→active（同事务）
            await conn.execute(
                "UPDATE crystal.claim SET status='superseded' WHERE id=$1",
                target_claim_id,
            )

        return {
            "correction_evidence_id": correction_evidence_id,
            "superseded_claim_id": target_claim_id,
            "new_claim_id": new_claim_id,
        }


async def reconcile_confirm(
    claim_id: str,
    owner_type: str,
    owner_id: str,
    actor_id: Optional[str] = None,
) -> Dict[str, Any]:
    """workbench confirm：用户认可当前 claim 为真 → +Δ content（强度 0.5 档，§4.1）。

    不建新边（workbench §3.1）；记 claim_activity + 计分。
    """
    async with db.get_connection() as conn:
        claim = await conn.fetchrow(
            """SELECT id, content_confidence, scope, owner_type, owner_id
               FROM crystal.claim
               WHERE id=$1 AND owner_type=$2 AND owner_id=$3""",
            claim_id,
            owner_type,
            owner_id,
        )
        if not claim:
            raise ValueError(f"Claim '{claim_id}' not found or not owned by you")

        current_conf = claim["content_confidence"]
        new_conf = reinforce_score(current_conf, STRENGTH_WEIGHTS["user_confirm"])
        await conn.execute(
            "UPDATE crystal.claim SET content_confidence=$1 WHERE id=$2",
            new_conf,
            claim_id,
        )
        await conn.execute(
            """INSERT INTO crystal.claim_activity
               (claim_id, action, actor_type, actor_id, triggered_by_evidence_id,
                detail, created_at)
               VALUES ($1, 'confirmed', 'user', $2, NULL, $3, NOW())""",
            claim_id,
            actor_id,
            json.dumps({"action": "confirm", "confidence_before": current_conf, "confidence_after": new_conf}),
        )
        return {"claim_id": claim_id, "content_confidence": new_conf}


async def reconcile_forget(
    claim_id: str,
    owner_type: str,
    owner_id: str,
    actor_id: Optional[str] = None,
    reason: str = "用户遗忘",
) -> Dict[str, Any]:
    """workbench forget：遗忘 = retract 边（to=NULL），该 claim 失活（§3.1 / workbench §3.1）。"""
    async with db.get_connection() as conn:
        claim = await conn.fetchrow(
            "SELECT id, owner_type, owner_id FROM crystal.claim WHERE id=$1 AND owner_type=$2 AND owner_id=$3",
            claim_id,
            owner_type,
            owner_id,
        )
        if not claim:
            raise ValueError(f"Claim '{claim_id}' not found or not owned by you")

        async with conn.transaction():
            # retract 边（单端 to=NULL）
            await conn.execute(
                """INSERT INTO crystal.lineage_edge
                   (from_claim_id, to_claim_id, edge_type, reason, created_at)
                   VALUES ($1, NULL, 'retract', $2, NOW())""",
                claim_id,
                reason,
            )
            # status 物化（同事务）
            await conn.execute(
                "UPDATE crystal.claim SET status='retracted' WHERE id=$1",
                claim_id,
            )
            # claim_activity
            await conn.execute(
                """INSERT INTO crystal.claim_activity
                   (claim_id, action, actor_type, actor_id, triggered_by_evidence_id,
                    detail, created_at)
                   VALUES ($1, 'retracted', 'user', $2, NULL, $3, NOW())""",
                claim_id,
                actor_id,
                json.dumps({"reason": reason}),
            )
        return {"claim_id": claim_id, "status": "retracted"}
    """同源复述闸门（§3.3）：E 与 claim 既有证据同源（source_ref 同一 session）→ True 不计分。"""
    session_id = (evidence.get("source_ref") or {}).get("session_id") if isinstance(evidence.get("source_ref"), dict) else None
    if not session_id:
        return False
    rows = await conn.fetch(
        """SELECT ce.evidence_id FROM crystal.claim_evidence ce
           JOIN crystal.evidence e ON e.id = ce.evidence_id
           WHERE ce.claim_id=$1 AND e.source_ref->>'session_id'=$2
           LIMIT 1""",
        claim_id,
        session_id,
    )
    return len(rows) > 0


async def _mark_isolated_for_review(evidence_id: str, reason: str) -> None:
    """超上限 evidence 隔离标记（claim-atomicity §4.2 / ADR-0020 #9）。

    不自动拆条/不对账；evidence 原文保留（Evidence 不可再生，不删）；
    evidence_processing 停留 pending（workbench「待裁决」视图可扫到）；
    在 claim_activity 留审计（workbench 待裁决列表依据）。
    """
    async with db.get_connection() as conn:
        await conn.execute(
            """UPDATE crystal.evidence_processing
               SET processing_state='pending', current_step='isolated', last_error=$1, updated_at=NOW()
               WHERE evidence_id=$2""",
            json.dumps({"step": "isolated", "message": f"双上限隔离: {reason}", "attempts": 0}),
            evidence_id,
        )


async def reconcile_evidence(evidence_id: str) -> Dict[str, Any]:
    """对账单条 evidence（worker 调用）。

    入口生成 trace_id（trace-id 计划 §3.1）：对账全链路（embedding → 拆条 LLM ① →
    碰撞 LLM ② → 批量写）的业务日志 + LLM client 日志自动带同一 [trace_id=ev_xxx]，
    可按 id 一键串联排查；函数返回（含异常路径）后清理，并发对账不串。
    """
    # 嵌套调用（如 reconcile/run 重跑多条）已有 trace → 沿用，不重复生成
    had_trace = get_trace_id() is not None
    if not had_trace:
        token = set_trace_id(generate_trace_id("ev"))
    try:
        return await _reconcile_evidence_impl(evidence_id)
    finally:
        if not had_trace:
            reset_trace_id(token)


async def _reconcile_evidence_impl(evidence_id: str) -> Dict[str, Any]:
    """对账单条 evidence 实现体（trace_id 由 reconcile_evidence 入口管理）。"""
    logger.info(f"crystal 对账开始: evidence={evidence_id}")
    async with db.get_connection() as conn:
        ev = await conn.fetchrow(
            """SELECT e.*, p.processing_state
               FROM crystal.evidence e
               LEFT JOIN crystal.evidence_processing p ON p.evidence_id = e.id
               WHERE e.id=$1""",
            evidence_id,
        )
        if not ev:
            logger.warning(f"crystal 对账: evidence {evidence_id} 不存在")
            return {"status": "not_found"}

        # 认领：pending/processing/failed → processing（CAS 防并发）
        claimed = await conn.execute(
            """UPDATE crystal.evidence_processing
               SET processing_state='processing', current_step='embedding', updated_at=NOW()
               WHERE evidence_id=$1 AND processing_state IN ('pending','processing','failed')""",
            evidence_id,
        )
        if "UPDATE 0" in claimed:
            return {"status": "already_processing"}

    try:
        # ② embedding 步
        embedding = await _embed(ev["content"])
        async with db.get_connection() as conn:
            if embedding:
                await conn.execute(
                    "UPDATE crystal.evidence SET embedding=$1 WHERE id=$2",
                    _embedding_to_str(embedding),
                    evidence_id,
                )
            await conn.execute(
                """UPDATE crystal.evidence_processing
                   SET current_step='reconcile', updated_at=NOW()
                   WHERE evidence_id=$1""",
                evidence_id,
            )

        evidence = dict(ev)
        evidence["embedding"] = embedding

        # ③ 对账步（M2.1：拆条流程，reconciliation-design §2.4）
        # user_correction 特权路径（§3.1）由 workbench correct 端点走 reconcile_correction
        # （见 workbench.py），不进通用碰撞路径

        # 双上限前置检查（claim-atomicity §4.2）：超限默认隔离，留存 workbench 待裁决
        if len(evidence["content"]) > MAX_EVIDENCE_CHARS:
            logger.info(
                f"crystal 对账: evidence {evidence_id} 超字数上限（{len(evidence['content'])} > {MAX_EVIDENCE_CHARS}），"
                f"默认隔离留存 workbench 待裁决"
            )
            await _mark_isolated_for_review(evidence_id, "evidence_too_long")
            return {"status": "isolated", "reason": "evidence_too_long"}

        # LLM ① 拆条（0..N 条原子 claim）
        logger.info(f"crystal 拆条 LLM ①: evidence={evidence_id} content_len={len(evidence['content'])}")
        decomposed = await _llm_decompose_claims(evidence)
        if not decomposed:
            # 拆条全部失败（长文本分块失败）→ 不把原文照抄进 claim（分层错误），
            # 标记隔离留存 workbench 人工裁决
            logger.warning(
                f"crystal 对账: evidence {evidence_id} 拆条失败（长文本），默认隔离留存 workbench 待裁决"
            )
            await _mark_isolated_for_review(evidence_id, "decompose_failed")
            return {"status": "isolated", "reason": "decompose_failed"}
        if len(decomposed) > MAX_CLAIMS_PER_EVIDENCE:
            logger.info(
                f"crystal 对账: evidence {evidence_id} 拆出 {len(decomposed)} 条超条目上限（{MAX_CLAIMS_PER_EVIDENCE}），"
                f"默认隔离留存 workbench 待裁决"
            )
            await _mark_isolated_for_review(evidence_id, "claims_too_many")
            return {"status": "isolated", "reason": "claims_too_many"}

        # 逐条检索候选（embedding，非 LLM；拆条后才知该查什么，§2.4 数据依赖顺序）
        # 给每条拆条产物分配临时 id（c1/c2/...），与 _write_reconcile_transaction_batch
        # 的 claim_ids 对齐（LLM ① 输出不含 id，id 是事务内临时标识）
        candidates_by_claim: Dict[str, List[Dict[str, Any]]] = {}
        for idx, c in enumerate(decomposed):
            cands = await _find_candidate_claims(
                evidence["owner_type"],
                evidence["owner_id"],
                evidence["scope"],
                embedding,
            )
            candidates_by_claim[f"c{idx + 1}"] = cands

        # LLM ② 碰撞判定批处理（N 条新 claim + 各自候选一次传入）
        logger.info(f"crystal 碰撞 LLM ②: evidence={evidence_id} claims={len(decomposed)}")
        judgments = await _llm_collision_judge_batch(evidence, decomposed, candidates_by_claim)

        # 单事务批量写
        result = await _write_reconcile_transaction_batch(evidence, decomposed, judgments)

        # ④ done
        async with db.get_connection() as conn:
            await conn.execute(
                """UPDATE crystal.evidence_processing
                   SET processing_state='done', current_step=NULL, last_error=NULL, updated_at=NOW()
                   WHERE evidence_id=$1""",
                evidence_id,
            )
        logger.info(
            f"crystal 对账完成: evidence={evidence_id} "
            f"created={len(result.get('created_claim_ids', []))} "
            f"superseded={len(result.get('superseded_ids', []))} "
            f"reinforced={len(result.get('reinforced_claim_ids', []))}"
        )
        return {"status": "done", **result}

    except Exception as e:
        logger.error(f"crystal 对账失败 evidence={evidence_id}: {e}")
        async with db.get_connection() as conn:
            # 重试计数（§5：attempts < 3 → pending 重试；≥3 → failed 停留）
            row = await conn.fetchrow(
                "SELECT last_error FROM crystal.evidence_processing WHERE evidence_id=$1",
                evidence_id,
            )
            attempts = 0
            last_error = row["last_error"] if row else None
            if last_error and isinstance(last_error, dict):
                attempts = last_error.get("attempts", 0)
            attempts += 1
            state = "failed" if attempts >= 3 else "pending"
            await conn.execute(
                """UPDATE crystal.evidence_processing
                   SET processing_state=$1, current_step='reconcile', last_error=$2, updated_at=NOW()
                   WHERE evidence_id=$3""",
                state,
                json.dumps({"step": "reconcile", "message": str(e), "attempts": attempts}),
                evidence_id,
            )
        return {"status": "failed", "error": str(e), "attempts": attempts}
