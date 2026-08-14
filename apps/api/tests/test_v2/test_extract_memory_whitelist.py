"""临时验证：extract-memory 类型白名单归一化"""
import asyncio
from unittest.mock import AsyncMock, patch
from src.api.memories import (
    extract_memory_from_summary,
    ExtractMemoryRequest,
)

def test_distill_type_whitelist_normalization():
    """未知/错拼类型必须归一为 learned-pattern（方案 B）"""
    with patch("src.llm.client.get_llm_client") as mock_llm:
        mock_llm.return_value.aextract_json = AsyncMock(return_value={
            "memories": [
                {"content": "好记忆1", "type": "preference", "reason": "偏好"},
                {"content": "好记忆2", "type": "learn-pattern", "reason": "错拼"},
                {"content": "好记忆3", "type": "weird-type", "reason": "乱填"},
                {"content": "", "type": "preference", "reason": "空内容应丢弃"},
            ]
        })
        resp = asyncio.run(
            extract_memory_from_summary(
                ExtractMemoryRequest(summary="测试", language="zh_CN"),
                container_tag="user_test",
            )
        )
    assert len(resp.memories) == 3, f"空内容应被过滤，实际 {len(resp.memories)}"
    types = [m.type for m in resp.memories]
    assert types[0] == "preference"
    assert types[1] == "learned-pattern", "错拼类型必须归一"
    assert types[2] == "learned-pattern", "未知类型必须归一"
    print("whitelist normalization OK:", types)
