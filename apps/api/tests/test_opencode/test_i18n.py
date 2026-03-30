"""
Unit tests for OpenCode plugin i18n module.
"""

import pytest


class TestLanguageDetection:
    def test_detect_chinese(self):
        from src.plugins.opencode.i18n import detect_language

        assert detect_language("这是一段中文文本") == "zh_CN"
        assert detect_language("你好世界") == "zh_CN"
        assert detect_language("请记住这个重要的信息") == "zh_CN"

    def test_detect_english(self):
        from src.plugins.opencode.i18n import detect_language

        assert detect_language("This is English text") == "en_US"
        assert detect_language("Hello world") == "en_US"
        assert detect_language("Please remember this important information") == "en_US"

    def test_detect_mixed_chinese_dominant(self):
        from src.plugins.opencode.i18n import detect_language

        text = "这是一段很长的中文文本有很多中文字符 with some English"
        assert detect_language(text) == "zh_CN"

    def test_detect_mixed_english_dominant(self):
        from src.plugins.opencode.i18n import detect_language

        text = "This is English text with 中文 words"
        assert detect_language(text) == "en_US"

    def test_detect_empty_text(self):
        from src.plugins.opencode.i18n import detect_language

        assert detect_language("") == "en_US"
        assert detect_language("   ") == "en_US"

    def test_detect_threshold_boundary(self):
        from src.plugins.opencode.i18n import detect_language

        chinese_chars = "记" * 40
        english_chars = "a" * 60

        text = chinese_chars + english_chars
        assert detect_language(text) == "zh_CN"

        chinese_chars = "记" * 20
        english_chars = "a" * 80

        text = chinese_chars + english_chars
        assert detect_language(text) == "en_US"


class TestKeywords:
    def test_get_chinese_keywords(self):
        from src.plugins.opencode.i18n import get_keywords

        keywords = get_keywords("zh_CN")

        assert "记住" in keywords
        assert "别忘了" in keywords
        assert "记下来" in keywords
        assert len(keywords) >= 10

    def test_get_english_keywords(self):
        from src.plugins.opencode.i18n import get_keywords

        keywords = get_keywords("en_US")

        assert "remember" in keywords
        assert "save this" in keywords
        assert "don't forget" in keywords
        assert len(keywords) >= 10

    def test_get_all_keywords(self):
        from src.plugins.opencode.i18n import get_all_keywords

        keywords = get_all_keywords()

        assert "记住" in keywords
        assert "remember" in keywords
        assert len(keywords) >= 25


class TestCompiledPattern:
    def test_chinese_keywords_available(self):
        from src.plugins.opencode.i18n import get_keywords

        keywords = get_keywords("zh_CN")

        assert "记住" in keywords
        assert "别忘了" in keywords
        assert "记下来" in keywords

    def test_pattern_matches_english(self):
        from src.plugins.opencode.i18n import get_compiled_keyword_pattern

        pattern = get_compiled_keyword_pattern()

        assert pattern.search("please remember this")
        assert pattern.search("save this for later")
        assert pattern.search("don't forget")

    def test_pattern_no_match(self):
        from src.plugins.opencode.i18n import get_compiled_keyword_pattern

        pattern = get_compiled_keyword_pattern()

        assert not pattern.search("hello world")
        assert not pattern.search("你好世界")

    def test_pattern_locale_specific(self):
        from src.plugins.opencode.i18n import get_compiled_keyword_pattern

        zh_pattern = get_compiled_keyword_pattern("zh_CN")
        en_pattern = get_compiled_keyword_pattern("en_US")

        assert zh_pattern.search("记住这个")
        assert en_pattern.search("remember this")


class TestNudgeMessages:
    def test_get_chinese_nudge(self):
        from src.plugins.opencode.i18n import get_nudge

        nudge = get_nudge("zh_CN")

        assert "[检测到记忆触发]" in nudge
        assert "memory-recall" in nudge
        assert "add" in nudge

    def test_get_english_nudge(self):
        from src.plugins.opencode.i18n import get_nudge

        nudge = get_nudge("en_US")

        assert "[MEMORY TRIGGER DETECTED]" in nudge
        assert "memory-recall" in nudge
        assert "add" in nudge


class TestContextFormatting:
    def test_format_context_chinese(self):
        from src.plugins.opencode.i18n import format_context

        result = format_context(
            locale_code="zh_CN",
            static_facts=["用户名：张三"],
            dynamic_facts=["正在做测试"],
            project_memories=[{"content": "项目信息", "similarity": 0.9}],
            user_memories=[],
        )

        assert "[记忆召回]" in result
        assert "用户画像" in result
        assert "项目知识" in result

    def test_format_context_english(self):
        from src.plugins.opencode.i18n import format_context

        result = format_context(
            locale_code="en_US",
            static_facts=["Username: John"],
            dynamic_facts=["Working on tests"],
            project_memories=[{"content": "Project info", "similarity": 0.9}],
            user_memories=[],
        )

        assert "[MEMORY-RECALL]" in result
        assert "User Profile" in result
        assert "Project Knowledge" in result

    def test_format_context_empty(self):
        from src.plugins.opencode.i18n import format_context

        result = format_context(
            locale_code="en_US",
            static_facts=[],
            dynamic_facts=[],
            project_memories=[],
            user_memories=[],
        )

        assert result == ""

    def test_format_context_with_similarity(self):
        from src.plugins.opencode.i18n import format_context

        result = format_context(
            locale_code="en_US",
            static_facts=[],
            dynamic_facts=[],
            project_memories=[
                {"content": "Info 1", "similarity": 0.95},
                {"content": "Info 2", "similarity": 0.80},
            ],
            user_memories=[],
        )

        assert "[95%]" in result
        assert "[80%]" in result


class TestResolveLocale:
    def test_resolve_auto_with_chinese_text(self):
        from src.plugins.opencode.i18n import resolve_locale

        result = resolve_locale("auto", "这是一段中文")
        assert result == "zh_CN"

    def test_resolve_auto_with_english_text(self):
        from src.plugins.opencode.i18n import resolve_locale

        result = resolve_locale("auto", "This is English")
        assert result == "en_US"

    def test_resolve_explicit_chinese(self):
        from src.plugins.opencode.i18n import resolve_locale

        result = resolve_locale("zh_CN", "This is English")
        assert result == "zh_CN"

    def test_resolve_explicit_english(self):
        from src.plugins.opencode.i18n import resolve_locale

        result = resolve_locale("en_US", "这是中文")
        assert result == "en_US"

    def test_resolve_invalid_defaults_to_english(self):
        from src.plugins.opencode.i18n import resolve_locale

        result = resolve_locale("invalid", "any text")
        assert result == "en_US"


class TestToolMessages:
    def test_get_tool_message_simple(self):
        from src.plugins.opencode.i18n import get_tool_message

        msg = get_tool_message("en_US", "memory_added")

        assert msg is not None

    def test_get_tool_message_with_formatting(self):
        from src.plugins.opencode.i18n import get_tool_message

        msg = get_tool_message("en_US", "memory_added", scope="project")

        assert "project" in msg

    def test_get_tool_message_missing_key(self):
        from src.plugins.opencode.i18n import get_tool_message

        msg = get_tool_message("en_US", "nonexistent_key")

        assert msg == "nonexistent_key"
