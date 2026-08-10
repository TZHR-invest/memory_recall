"""Tests for detect_is_static rule-based classification.

Golden cases document the current rule behavior, including known blind
spots (rules cannot understand semantics). These serve as regression
baseline if the word list is ever tuned.
"""

import sys
import os

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from src.services.core.asmr_entity_types import detect_is_static


class TestDetectIsStatic:
    def test_static_with_static_indicator(self):
        assert detect_is_static("用户喜欢喝美式咖啡") is True

    def test_static_occupation(self):
        assert detect_is_static("我的职业是软件工程师") is True

    def test_dynamic_with_dynamic_indicator(self):
        assert detect_is_static("今天去看了电影") is False

    def test_dynamic_recent_activity(self):
        assert detect_is_static("最近在做一个项目") is False

    def test_dynamic_operation_log(self):
        assert detect_is_static("TrendRadar飞书推送用trendradar_feishu_push.py 08:00运行") is False

    def test_dynamic_hot_topic(self):
        assert detect_is_static("特朗普宣布向关键矿产投资30亿美元补链供应链") is False

    def test_dynamic_cache_notes(self):
        assert detect_is_static("stock_current/get_dcf_data 缓存机制要点记录") is False

    def test_static_preference_list(self):
        assert detect_is_static("用户偏好漫剧制作, 解说层必须独立声线") is True

    def test_both_indicators_defaults_dynamic(self):
        assert detect_is_static("最近决定坚持每天跑步") is False

    def test_no_indicator_defaults_dynamic(self):
        assert detect_is_static("我吃素") is False
