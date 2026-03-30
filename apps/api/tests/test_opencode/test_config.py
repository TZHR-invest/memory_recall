"""
Unit tests for OpenCode plugin configuration loader.
"""

import pytest
import os
import tempfile
import json
from pathlib import Path


class TestConfigLoader:
    def test_default_values(self):
        from src.plugins.opencode.config import Config

        config = Config()

        assert config.api_key is None
        assert config.base_url == "http://localhost:8000"
        assert config.container_tag_prefix == "memory-recall"
        assert config.similarity_threshold == 0.6
        assert config.max_memories == 5
        assert config.max_project_memories == 10
        assert config.compaction_threshold == 0.8
        assert config.enable_summary_capture is True
        assert config.enable_document_tracking is True
        assert config.language == "auto"
        assert config.log_level == "info"

    def test_validation_compaction_threshold(self):
        from src.plugins.opencode.config import Config

        config = Config(compaction_threshold=1.5)
        assert config.compaction_threshold == 0.8

        config = Config(compaction_threshold=-0.1)
        assert config.compaction_threshold == 0.8

        config = Config(compaction_threshold=0.5)
        assert config.compaction_threshold == 0.5

    def test_validation_similarity_threshold(self):
        from src.plugins.opencode.config import Config

        config = Config(similarity_threshold=1.5)
        assert config.similarity_threshold == 0.6

        config = Config(similarity_threshold=-0.1)
        assert config.similarity_threshold == 0.6

    def test_validation_language(self):
        from src.plugins.opencode.config import Config

        config = Config(language="invalid")
        assert config.language == "auto"

        config = Config(language="zh_CN")
        assert config.language == "zh_CN"

        config = Config(language="en_US")
        assert config.language == "en_US"

    def test_is_configured(self):
        from src.plugins.opencode.config import Config

        config = Config()
        assert config.is_configured() is False

        config = Config(api_key="rk_live_test")
        assert config.is_configured() is True

    def test_get_all_keyword_patterns(self):
        from src.plugins.opencode.config import Config

        config = Config()
        patterns = config.get_all_keyword_patterns()

        assert "remember" in patterns
        assert "记住" in patterns
        assert len(patterns) >= 30

    def test_compiled_keyword_pattern(self):
        from src.plugins.opencode.config import Config

        config = Config()
        pattern = config.get_compiled_keyword_pattern()

        assert pattern.search("please remember this")
        assert not pattern.search("no keywords here")

    def test_chinese_keywords_in_list(self):
        from src.plugins.opencode.config import DEFAULT_CHINESE_KEYWORDS

        assert "记住" in DEFAULT_CHINESE_KEYWORDS
        assert "别忘了" in DEFAULT_CHINESE_KEYWORDS


class TestStripJsoncComments:
    def test_single_line_comments(self):
        from src.plugins.opencode.config import strip_jsonc_comments

        content = """
{
  "key": "value", // this is a comment
  "other": "value"
}
"""
        result = strip_jsonc_comments(content)
        assert "// this is a comment" not in result
        assert '"key": "value"' in result

    def test_multi_line_comments(self):
        from src.plugins.opencode.config import strip_jsonc_comments

        content = """
{
  /* multi
  line
  comment */
  "key": "value"
}
"""
        result = strip_jsonc_comments(content)
        assert "/* multi" not in result
        assert "comment */" not in result
        assert '"key": "value"' in result

    def test_no_comments(self):
        from src.plugins.opencode.config import strip_jsonc_comments

        content = '{"key": "value"}'
        result = strip_jsonc_comments(content)
        assert result == content


class TestContainerTagGeneration:
    def test_generate_container_tag(self):
        from src.plugins.opencode.config import generate_container_tag

        tag = generate_container_tag("test", "user@example.com", "user")

        assert tag.startswith("test_user_")
        assert len(tag) == len("test_user_") + 16

    def test_generate_container_tag_deterministic(self):
        from src.plugins.opencode.config import generate_container_tag

        tag1 = generate_container_tag("test", "user@example.com", "user")
        tag2 = generate_container_tag("test", "user@example.com", "user")

        assert tag1 == tag2

    def test_generate_container_tag_different_inputs(self):
        from src.plugins.opencode.config import generate_container_tag

        tag1 = generate_container_tag("test", "user1@example.com", "user")
        tag2 = generate_container_tag("test", "user2@example.com", "user")

        assert tag1 != tag2


class TestConfigFileLoading:
    def test_load_config_file_json(self):
        from src.plugins.opencode.config import load_config_file

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"apiKey": "test_key", "maxMemories": 10}, f)
            f.flush()

            result = load_config_file(Path(f.name))

            assert result["apiKey"] == "test_key"
            assert result["maxMemories"] == 10

            os.unlink(f.name)

    def test_load_config_file_jsonc(self):
        from src.plugins.opencode.config import load_config_file

        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonc", delete=False) as f:
            f.write('{"key": "value", // comment\n"other": "value"}')
            f.flush()

            result = load_config_file(Path(f.name))

            assert result["key"] == "value"
            assert result["other"] == "value"

            os.unlink(f.name)

    def test_load_config_file_not_exists(self):
        from src.plugins.opencode.config import load_config_file

        result = load_config_file(Path("/nonexistent/config.json"))
        assert result == {}


class TestEnvOverrides:
    def test_env_override_api_key(self, monkeypatch):
        from src.plugins.opencode.config import load_config

        monkeypatch.setenv("MEMORY_RECALL_API_KEY", "env_key")

        config = load_config()

        assert config.api_key == "env_key"

        monkeypatch.delenv("MEMORY_RECALL_API_KEY")

    def test_env_override_base_url(self, monkeypatch):
        from src.plugins.opencode.config import load_config

        monkeypatch.setenv("MEMORY_RECALL_BASE_URL", "http://custom:9000")

        config = load_config()

        assert config.base_url == "http://custom:9000"

        monkeypatch.delenv("MEMORY_RECALL_BASE_URL")

    def test_env_override_language(self, monkeypatch):
        from src.plugins.opencode.config import load_config

        monkeypatch.setenv("MEMORY_RECALL_LANGUAGE", "zh_CN")

        config = load_config()

        assert config.language == "zh_CN"

        monkeypatch.delenv("MEMORY_RECALL_LANGUAGE")


class TestCamelCaseToSnakeCase:
    def test_camel_case_conversion(self):
        from src.plugins.opencode.config import load_config

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(
                {
                    "apiKey": "test",
                    "baseUrl": "http://test",
                    "maxMemories": 20,
                    "compactionThreshold": 0.9,
                },
                f,
            )
            f.flush()

            original_home = os.environ.get("HOME")
            temp_home = tempfile.mkdtemp()
            os.environ["HOME"] = temp_home

            config_dir = Path(temp_home) / ".config" / "opencode"
            config_dir.mkdir(parents=True, exist_ok=True)

            import shutil

            shutil.copy(f.name, config_dir / "memory-recall.json")

            config = load_config()

            assert config.api_key == "test"
            assert config.base_url == "http://test"
            assert config.max_memories == 20
            assert config.compaction_threshold == 0.9

            os.unlink(f.name)
            if original_home:
                os.environ["HOME"] = original_home
            else:
                del os.environ["HOME"]
            shutil.rmtree(temp_home)
