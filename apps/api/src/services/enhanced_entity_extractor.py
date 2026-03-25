"""
增强的实体提取服务
解决实体词典精确匹配的局限性

问题场景：
- 词典: "新技能学习"
- 查询: "学习了什么新技能"
- 结果: 精确匹配失败 ❌

解决方案：
1. 关键词匹配（分词后匹配）
2. 模糊匹配（编辑距离）
3. 语义相似度匹配（embedding）
4. 正则表达式匹配
5. 混合策略
"""

from typing import List, Dict, Optional, Tuple
import re
from difflib import SequenceMatcher
from ..database import db
import logging

logger = logging.getLogger(__name__)


class EnhancedEntityExtractor:
    """增强的实体提取器"""

    def __init__(self):
        self.entity_dict: Dict[str, Dict] = {}
        self.entity_embeddings: Dict[str, List[float]] = {}
        self._initialized = False

        # 停用词
        self.stopwords = {
            "的",
            "了",
            "在",
            "是",
            "我",
            "有",
            "和",
            "就",
            "不",
            "人",
            "都",
            "一",
            "一个",
            "上",
            "也",
            "很",
            "到",
            "说",
            "要",
            "去",
            "你",
            "会",
            "什么",
            "怎么",
            "为什么",
            "哪",
            "哪个",
            "哪些",
        }

        # 自动刷新配置
        self._last_refresh_time = None
        self._auto_refresh_interval = 300  # 5分钟自动刷新

    async def initialize(self):
        """
        初始化实体词典
        """
        if self._initialized:
            return

        # 加载所有实体
        users = await db.fetch("SELECT id FROM public.users")

        for user in users:
            user_id = user["id"]
            async with db.user_context(user_id):
                entities = await db.fetch(
                    """
                    SELECT id, name, type, confidence, user_id
                    FROM entities
                    WHERE confidence >= 0.5
                    ORDER BY mention_count DESC
                    """
                )

                for entity in entities:
                    entity_name = entity["name"]
                    self.entity_dict[entity_name] = {
                        "id": str(entity["id"]),
                        "type": entity["type"],
                        "confidence": entity["confidence"],
                        "user_id": entity["user_id"],
                    }

        self._initialized = True
        self._last_refresh_time = time.time()
        logger.info(f"实体词典初始化完成，共 {len(self.entity_dict)} 个实体")

    def add_entity(self, entity_name: str, entity_info: Dict):
        """
        添加单个实体到词典（用于增量更新）

        Args:
            entity_name: 实体名称
            entity_info: 实体信息
        """
        if entity_name in self.entity_dict:
            existing = self.entity_dict[entity_name]
            if isinstance(existing, list):
                existing.append(entity_info)
            else:
                self.entity_dict[entity_name] = [existing, entity_info]
        else:
            self.entity_dict[entity_name] = entity_info

        logger.info(f"实体词典增量更新: {entity_name}")

    async def check_and_refresh(self):
        """
        检查并自动刷新词典（定时刷新机制）

        如果距离上次刷新超过 5 分钟，则自动刷新
        """
        if not self._last_refresh_time:
            return

        current_time = time.time()
        elapsed = current_time - self._last_refresh_time

        if elapsed > self._auto_refresh_interval:
            logger.info(f"触发自动刷新（距离上次刷新 {elapsed:.0f}秒）")
            await self.refresh()

    def extract_entities(
        self, query: str, user_id: str, methods: List[str] = None
    ) -> List[Tuple[str, str, float]]:
        """
        提取实体（多策略）

        Args:
            query: 查询文本
            user_id: 用户 ID
            methods: 使用的方法列表，默认使用所有方法
                - "exact": 精确匹配
                - "keyword": 关键词匹配
                - "fuzzy": 模糊匹配
                - "semantic": 语义匹配
                - "regex": 正则匹配

        Returns:
            [(实体名称, 匹配方法, 置信度), ...]
        """
        if not self._initialized:
            logger.warning("实体词典未初始化")
            return []

        # 自动刷新检查（兜底机制）
        import asyncio

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(self.check_and_refresh())
        except:
            pass

        if methods is None:
            methods = ["exact", "keyword", "fuzzy", "semantic"]

        results = []
        seen_entities = set()

        # 过滤用户实体
        user_entities = {
            name: info
            for name, info in self.entity_dict.items()
            if info.get("user_id") == user_id
        }

        # 1. 精确匹配
        if "exact" in methods:
            exact_matches = self._exact_match(query, user_entities)
            for entity_name, confidence in exact_matches:
                if entity_name not in seen_entities:
                    results.append((entity_name, "exact", confidence))
                    seen_entities.add(entity_name)

        # 2. 关键词匹配
        if "keyword" in methods:
            keyword_matches = self._keyword_match(query, user_entities)
            for entity_name, confidence in keyword_matches:
                if entity_name not in seen_entities:
                    results.append((entity_name, "keyword", confidence))
                    seen_entities.add(entity_name)

        # 3. 模糊匹配
        if "fuzzy" in methods:
            fuzzy_matches = self._fuzzy_match(query, user_entities, threshold=0.6)
            for entity_name, confidence in fuzzy_matches:
                if entity_name not in seen_entities:
                    results.append((entity_name, "fuzzy", confidence))
                    seen_entities.add(entity_name)

        # 4. 语义匹配
        if "semantic" in methods:
            semantic_matches = await self._semantic_match(
                query, user_entities, threshold=0.75
            )
            for entity_name, confidence in semantic_matches:
                if entity_name not in seen_entities:
                    results.append((entity_name, "semantic", confidence))
                    seen_entities.add(entity_name)

        # 5. 正则匹配
        if "regex" in methods:
            regex_matches = self._regex_match(query, user_entities)
            for entity_name, confidence in regex_matches:
                if entity_name not in seen_entities:
                    results.append((entity_name, "regex", confidence))
                    seen_entities.add(entity_name)

        # 按置信度排序
        results.sort(key=lambda x: x[2], reverse=True)

        return results

    def _exact_match(self, query: str, user_entities: Dict) -> List[Tuple[str, float]]:
        """
        精确匹配（字符串包含）

        示例:
            查询: "张三的朋友"
            匹配: "张三"
        """
        matches = []

        for entity_name in sorted(user_entities.keys(), key=len, reverse=True):
            if entity_name in query:
                matches.append((entity_name, 1.0))

        return matches

    def _keyword_match(
        self, query: str, user_entities: Dict
    ) -> List[Tuple[str, float]]:
        """
        关键词匹配（分词后匹配）

        解决问题:
            查询: "学习了什么新技能"
            词典: "新技能学习"
            结果: 匹配成功（共享关键词: "学习", "新技能"）

        原理:
            1. 对查询和实体名称分别分词
            2. 计算关键词重叠率
            3. 重叠率高则认为匹配
        """
        matches = []

        # 查询分词
        query_keywords = self._tokenize(query)
        query_keywords = [kw for kw in query_keywords if kw not in self.stopwords]

        for entity_name, entity_info in user_entities.items():
            # 实体名称分词
            entity_keywords = self._tokenize(entity_name)

            # 计算关键词重叠
            overlap = set(query_keywords) & set(entity_keywords)

            if overlap:
                # 计算重叠率
                overlap_ratio = len(overlap) / max(
                    len(query_keywords), len(entity_keywords)
                )

                # 至少 2 个关键词重叠，或重叠率 > 0.5
                if len(overlap) >= 2 or overlap_ratio > 0.5:
                    confidence = min(1.0, overlap_ratio + 0.2)
                    matches.append((entity_name, confidence))

        return matches

    def _fuzzy_match(
        self, query: str, user_entities: Dict, threshold: float = 0.6
    ) -> List[Tuple[str, float]]:
        """
        模糊匹配（编辑距离）

        解决问题:
            查询: "新技能"
            词典: "新技能学习"
            结果: 相似度 0.67，匹配成功

        使用 SequenceMatcher 计算相似度
        """
        matches = []

        # 从查询中提取可能的实体片段
        query_segments = self._extract_segments(query, min_length=2)

        for segment in query_segments:
            for entity_name in user_entities.keys():
                # 计算相似度
                similarity = SequenceMatcher(None, segment, entity_name).ratio()

                if similarity >= threshold:
                    matches.append((entity_name, similarity))

        # 去重，保留最高相似度
        seen = {}
        for entity_name, confidence in matches:
            if entity_name not in seen or seen[entity_name] < confidence:
                seen[entity_name] = confidence

        return [(k, v) for k, v in seen.items()]

    async def _semantic_match(
        self, query: str, user_entities: Dict, threshold: float = 0.75
    ) -> List[Tuple[str, float]]:
        """
        语义匹配（embedding 相似度）

        解决问题:
            查询: "学的新东西"
            词典: "新技能学习"
            结果: 语义相似度 0.85，匹配成功

        使用 embedding 计算语义相似度
        """
        matches = []

        try:
            from ..embedding.client import get_embedding_client

            embedding_client = get_embedding_client()

            # 生成查询向量
            query_embedding = embedding_client.embed(query)

            if not query_embedding:
                return []

            # 生成实体向量（缓存）
            if not self.entity_embeddings:
                for entity_name in user_entities.keys():
                    self.entity_embeddings[entity_name] = embedding_client.embed(
                        entity_name
                    )

            # 计算相似度
            import numpy as np

            query_vec = np.array(query_embedding)

            for entity_name, entity_vec in self.entity_embeddings.items():
                if entity_name not in user_entities:
                    continue

                entity_vec = np.array(entity_vec)

                # 余弦相似度
                similarity = np.dot(query_vec, entity_vec) / (
                    np.linalg.norm(query_vec) * np.linalg.norm(entity_vec)
                )

                if similarity >= threshold:
                    matches.append((entity_name, float(similarity)))

        except Exception as e:
            logger.error(f"语义匹配失败: {e}")

        return matches

    def _regex_match(self, query: str, user_entities: Dict) -> List[Tuple[str, float]]:
        """
        正则表达式匹配

        解决问题:
            查询: "学习XXX新技能"  (XXX是干扰词)
            词典: "新技能学习"
            结果: 通过正则表达式模式匹配
        """
        matches = []

        for entity_name in user_entities.keys():
            # 构建正则模式
            # 允许中间插入一些字符
            pattern = ".*?".join(re.escape(char) for char in entity_name)

            if re.search(pattern, query):
                matches.append((entity_name, 0.8))

        return matches

    def _tokenize(self, text: str) -> List[str]:
        """
        分词（使用 jieba）
        """
        import jieba

        words = jieba.cut(text)
        return [w for w in words if len(w) >= 2 and w not in self.stopwords]

    def _extract_segments(self, text: str, min_length: int = 2) -> List[str]:
        """
        提取文本片段（用于模糊匹配）

        示例:
            输入: "学习了什么新技能"
            输出: ["学习", "新技能", "技能", ...]
        """
        segments = []

        # 使用 jieba 分词
        words = self._tokenize(text)
        segments.extend(words)

        # 提取连续片段
        for i in range(len(text)):
            for j in range(i + min_length, min(i + 10, len(text) + 1)):
                segment = text[i:j]
                if len(segment) >= min_length:
                    segments.append(segment)

        return list(set(segments))

    async def refresh(self):
        """
        刷新词典（重新从数据库加载所有实体）

        用途：
        1. 定时刷新（兜底机制）
        2. 手动刷新（管理员操作）
        """
        logger.info("刷新实体词典...")

        # 标记为未初始化，强制重新加载
        self._initialized = False
        self.entity_dict.clear()
        self.entity_embeddings.clear()

        await self.initialize()

        logger.info(f"实体词典刷新完成，共 {len(self.entity_dict)} 个实体")


# 全局实例
enhanced_entity_extractor: Optional[EnhancedEntityExtractor] = None


def get_enhanced_entity_extractor() -> EnhancedEntityExtractor:
    """获取增强实体提取器实例"""
    global enhanced_entity_extractor
    if enhanced_entity_extractor is None:
        enhanced_entity_extractor = EnhancedEntityExtractor()
    return enhanced_entity_extractor
