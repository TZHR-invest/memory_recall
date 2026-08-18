"""
crystal 鉴权映射（api-contract §1）

- owner_type/owner_id 由鉴权层从 API key 解析（客户端不可传，防越权）
- scope 由客户端显式传（不含 key_id 前缀），服务端校验归属，落库只存 scope 部分
- P0 阶段 owner_type 恒为 personal

归属校验语义（api-contract §1.2 + 2026-08-18 M1 实现拍板）：
  合法 scope：
    1. scope == NULL → 全局（user 级容器 {keyId}），落库 NULL
    2. scope 不以 keyId 形态开头（见下）→ 项目级 <dir> 部分，落库 scope
    3. 其他 → 403
  关键：客户端若把 keyId 拼进 scope（"{keyId}_xxx" 或任意 uuid 形态 "_" 前缀），
  属于"把 v5 container_tag 语义塞回 scope"——crystal 已拆分 owner，必须拒绝，
  否则 key A 写 scope="<B的keyId>_x"、key B 读同 scope 即串数据（越权）。
  真正的数据隔离靠 (owner_id, scope) 双键：查询恒带 owner_id=鉴权层解析值。
"""

import re
from typing import Dict, Optional

from .errors import CrystalAPIError

# keyId 形态：uuid（auth.py key_id = str(uuid.uuid4())）
_KEY_ID_PREFIX_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}_"
)


def owner_from_user(current_user: Dict) -> Dict[str, str]:
    """从鉴权层 user 字典解析 crystal owner（P0 恒 personal）。"""
    return {
        "owner_type": "personal",
        "owner_id": str(current_user["key_id"]),
    }


def verify_scope_ownership(scope: Optional[str], api_key_id: str) -> Optional[str]:
    """校验 scope 归属，返回可落库的 scope 值（None=全局）。

    Raises CrystalAPIError(403) 当：
      - scope 以 {api_key_id}_ 开头（客户端把 v5 container_tag 语义塞回 scope）
      - scope 以任意 uuid 形态 + "_" 开头（他人 keyId 伪装，防跨 key 串数据）
    """
    if scope is None:
        return None

    if scope.startswith(f"{api_key_id}_"):
        raise CrystalAPIError(
            403,
            "Scope must not contain the API key prefix. "
            "Pass the project part only (e.g. 'project-memory_recall'); "
            "owner_id is resolved from your API key automatically.",
        )

    if _KEY_ID_PREFIX_RE.match(scope):
        raise CrystalAPIError(
            403,
            "Scope must not start with a key-id shaped prefix "
            "(uuid + '_'). Scope is project-part only; ownership is "
            "resolved from your API key.",
        )

    return scope


def build_full_scope(scope: Optional[str], api_key_id: str) -> Optional[str]:
    """把客户端 scope 还原为 v5 语义的完整 container_tag（调试/迁移对照用）。"""
    if scope is None:
        return api_key_id
    return f"{api_key_id}_{scope}"
