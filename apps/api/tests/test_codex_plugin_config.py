"""Memory Recall Codex 插件 config.py 单元测试（无第三方依赖）。"""

import io
import json
import os
import sys
import time
from pathlib import Path

import pytest

PLUGIN_DIR = Path(__file__).resolve().parents[1] / "src" / "plugins" / "memory-recall-codex"
sys.path.insert(0, str(PLUGIN_DIR))

import config as config_mod  # noqa: E402
from config import detect_project_tag, load_config, strip_jsonc_comments  # noqa: E402


class TestStripJsoncComments:
    def test_url_not_mangled(self):
        # 回归：naive 的 // 正则会把 http:// 截断，导致整个配置解析失败
        raw = '{\n    "base_url": "http://localhost:8000",\n    "api_key": "rk_live_abc"\n}\n'
        assert strip_jsonc_comments(raw) == raw

    def test_line_comments_removed(self):
        raw = "{\n    // 注释\n    \"a\": 1\n}\n"
        assert strip_jsonc_comments(raw) == "{\n    \n    \"a\": 1\n}\n"

    def test_block_comments_removed(self):
        raw = "{\n    /* 块注释 */\n    \"a\": 1\n}\n"
        assert strip_jsonc_comments(raw) == "{\n    \n    \"a\": 1\n}\n"

    def test_slash_inside_string_kept(self):
        raw = '{"url": "https://example.com/a//b", "x": 1}\n'
        assert strip_jsonc_comments(raw) == raw

    def test_trailing_comma_removed(self):
        raw = "{\n    \"a\": 1,\n}\n"
        assert strip_jsonc_comments(raw) == "{\n    \"a\": 1\n}\n"

    def test_escaped_quote_in_string(self):
        raw = '{"a": "say \"hi\"", "b": 2}\n'
        assert strip_jsonc_comments(raw) == raw


class TestLoadConfig:
    def test_defaults(self, tmp_path):
        cfg = load_config(tmp_path / "missing.jsonc")
        assert cfg["base_url"] == "http://localhost:8000"
        assert cfg["api_key"] == ""

    def test_file_values_override_defaults(self, tmp_path):
        p = tmp_path / "memory-recall.jsonc"
        p.write_text('{\n  // 注释\n  "base_url": "http://127.0.0.1:9999",\n  "api_key": "rk_test_x",\n}\n', encoding="utf-8")
        cfg = load_config(p)
        assert cfg["base_url"] == "http://127.0.0.1:9999"
        assert cfg["api_key"] == "rk_test_x"

    def test_env_overrides_file(self, tmp_path, monkeypatch):
        p = tmp_path / "memory-recall.jsonc"
        p.write_text('{"user_tag": "from-file"}\n', encoding="utf-8")
        monkeypatch.setenv("MEMORY_RECALL_USER_TAG", "from-env")
        cfg = load_config(p)
        assert cfg["user_tag"] == "from-env"

    def test_broken_file_falls_back(self, tmp_path):
        p = tmp_path / "memory-recall.jsonc"
        p.write_text("{ 未闭合 \"a\": }\n", encoding="utf-8")
        cfg = load_config(p)
        assert cfg["base_url"] == "http://localhost:8000"
        assert cfg["api_key"] == ""

    def test_empty_values_ignored(self, tmp_path):
        p = tmp_path / "memory-recall.jsonc"
        p.write_text('{"api_key": "", "user_tag": "x"}\n', encoding="utf-8")
        cfg = load_config(p)
        assert cfg["api_key"] == ""
        assert cfg["user_tag"] == "x"


class TestDetectProjectTag:
    """父进程 cwd 自动生成 project_tag（模拟 opencode 的 input.directory 行为）。"""

    def test_codex_cli_parent_generates_tag(self, monkeypatch):
        monkeypatch.setattr(os, "getppid", lambda: 12345)
        monkeypatch.setattr("builtins.open", lambda *a, **k: io.BytesIO(b"codex exec --json"))
        monkeypatch.setattr(os, "readlink", lambda p: "/home/u/projects/myproj")
        assert detect_project_tag("k1") == "k1_project-myproj"

    def test_app_server_parent_falls_back(self, monkeypatch):
        # VSCode 扩展模式：父进程是 codex app-server，cwd 无意义 → 回退
        monkeypatch.setattr(os, "getppid", lambda: 12345)
        monkeypatch.setattr("builtins.open", lambda *a, **k: io.BytesIO(b"codex app-server"))
        monkeypatch.setattr(os, "readlink", lambda p: "/home/u/projects/myproj")
        monkeypatch.setattr(config_mod, "_detect_from_rollout", lambda u: None)
        monkeypatch.setattr(config_mod, "_detect_from_git", lambda u: None)
        assert detect_project_tag("k1", fallback="fb") == "fb"

    def test_home_cwd_falls_back(self, monkeypatch):
        monkeypatch.setattr(os, "getppid", lambda: 12345)
        monkeypatch.setattr("builtins.open", lambda *a, **k: io.BytesIO(b"codex exec"))
        monkeypatch.setattr(os, "readlink", lambda p: str(Path.home()))
        monkeypatch.setattr(config_mod, "_detect_from_rollout", lambda u: None)
        monkeypatch.setattr(config_mod, "_detect_from_git", lambda u: None)
        assert detect_project_tag("k1", fallback="fb") == "fb"

    def test_readlink_error_falls_back(self, monkeypatch):
        monkeypatch.setattr(os, "getppid", lambda: 12345)
        monkeypatch.setattr("builtins.open", lambda *a, **k: io.BytesIO(b"codex exec"))

        def boom(p):
            raise OSError("no proc")

        monkeypatch.setattr(os, "readlink", boom)
        monkeypatch.setattr(config_mod, "_detect_from_rollout", lambda u: None)
        monkeypatch.setattr(config_mod, "_detect_from_git", lambda u: None)
        assert detect_project_tag("k1", fallback="fb") == "fb"

    def test_cmdline_read_error_falls_back(self, monkeypatch):
        monkeypatch.setattr(os, "getppid", lambda: 12345)

        def boom(*a, **k):
            raise OSError("no proc")

        monkeypatch.setattr("builtins.open", boom)
        monkeypatch.setattr(os, "readlink", lambda p: "/home/u/projects/myproj")
        monkeypatch.setattr(config_mod, "_detect_from_rollout", lambda u: None)
        monkeypatch.setattr(config_mod, "_detect_from_git", lambda u: None)
        assert detect_project_tag("k1", fallback="fb") == "fb"

    def test_explicit_config_wins_over_auto(self, tmp_path):
        # 显式 project_tag 永远优先，不被自动探测覆盖
        p = tmp_path / "memory-recall.jsonc"
        p.write_text('{"project_tag": "k1_project-explicit", "user_tag": "k1"}\n', encoding="utf-8")
        cfg = load_config(p)
        assert cfg["project_tag"] == "k1_project-explicit"

    def test_git_fallback_generates_tag(self, monkeypatch):
        # VSCode 模式 + 插件位于 git 仓库：git 兜底生成 tag
        monkeypatch.setattr(config_mod, "_detect_from_parent", lambda u: None)
        monkeypatch.setattr(config_mod, "_detect_from_rollout", lambda u: None)
        monkeypatch.setattr(
            "subprocess.run",
            lambda *a, **k: type("R", (), {"returncode": 0, "stdout": "/home/u/repos/myrepo\n"})(),
        )
        assert detect_project_tag("k1") == "k1_project-myrepo"

    def test_git_failure_falls_back(self, monkeypatch):
        monkeypatch.setattr(config_mod, "_detect_from_parent", lambda u: None)
        monkeypatch.setattr(config_mod, "_detect_from_rollout", lambda u: None)
        monkeypatch.setattr(
            "subprocess.run",
            lambda *a, **k: type("R", (), {"returncode": 128, "stdout": ""})(),
        )
        assert detect_project_tag("k1", fallback="fb") == "fb"

    def test_codex_cli_detection_excludes_path_lookalikes(self):
        # 回归：路径含 codex 的进程（venv、opencodex）不能误判为 codex CLI
        assert config_mod._is_codex_cli_parent("/usr/local/bin/codex exec --json") is True
        assert config_mod._is_codex_cli_parent("codex exec --json") is True
        assert config_mod._is_codex_cli_parent("codex.exe exec") is True
        assert config_mod._is_codex_cli_parent("codex app-server --port 1") is False
        assert config_mod._is_codex_cli_parent("codex-code-mode-host") is False
        assert config_mod._is_codex_cli_parent(
            "/home/wbaifan/.config/codex/memory-recall-venv/bin/python server.py",
        ) is False
        assert config_mod._is_codex_cli_parent(
            "/home/wbaifan/.npm-global/lib/node_modules/@bitkyc08/opencodex/src/cli/index.ts start",
        ) is False


class TestDetectFromRollout:
    """~/.codex/sessions rollout 文件匹配（VSCode 模式定位当前会话 cwd）。"""

    @staticmethod
    def _make_rollout(sessions: Path, name: str, cwd: str) -> None:
        p = sessions / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(
            '{"type":"session_meta","payload":{"cwd":' + json.dumps(cwd) + "}}\n",
            encoding="utf-8",
        )

    def test_matches_closest_rollout(self, tmp_path):
        now = time.time()
        self._make_rollout(tmp_path, "rollout-2026-08-13T10-00-00-abc.jsonl", "/home/u/proj/old")
        close_name = time.strftime("rollout-%Y-%m-%dT%H-%M-%S-", time.localtime(now)) + "xyz.jsonl"
        self._make_rollout(tmp_path, close_name, "/home/u/proj/current")
        assert config_mod._detect_from_rollout("k1", sessions_dir=tmp_path, start_time=now) == "k1_project-current"


    def test_bad_cwd_rejected(self, tmp_path):
        now = time.time()
        close_name = time.strftime("rollout-%Y-%m-%dT%H-%M-%S-", time.localtime(now)) + "x.jsonl"
        self._make_rollout(tmp_path, close_name, "/tmp")
        assert config_mod._detect_from_rollout("k1", sessions_dir=tmp_path, start_time=now) is None

    def test_corrupt_file_returns_none(self, tmp_path):
        now = time.time()
        close_name = time.strftime("rollout-%Y-%m-%dT%H-%M-%S-", time.localtime(now)) + "x.jsonl"
        (tmp_path / close_name).write_text("not json\n", encoding="utf-8")
        assert config_mod._detect_from_rollout("k1", sessions_dir=tmp_path, start_time=now) is None

    def test_mtime_fallback_covers_restart(self, tmp_path):
        # 长会话 + server 重启：文件名时间戳超窗（3 小时前），但文件 mtime 新鲜（活跃写入）
        now = time.time()
        old_name = time.strftime("rollout-%Y-%m-%dT%H-%M-%S-", time.localtime(now - 10800)) + "x.jsonl"
        p = tmp_path / old_name
        p.write_text(
            '{"type":"session_meta","payload":{"cwd":"/home/u/proj/other"}}\n',
            encoding="utf-8",
        )
        os.utime(p, (now - 60, now - 60))  # mtime：1 分钟前还在写入
        assert config_mod._detect_from_rollout("k1", sessions_dir=tmp_path, start_time=now) == "k1_project-other"

    def test_mtime_outside_window_returns_none(self, tmp_path):
        # 文件 mtime 也超窗（会话已停止很久）→ 无命中，交给 git 兜底
        now = time.time()
        old_name = time.strftime("rollout-%Y-%m-%dT%H-%M-%S-", time.localtime(now - 10800)) + "x.jsonl"
        p = tmp_path / old_name
        p.write_text(
            '{"type":"session_meta","payload":{"cwd":"/home/u/proj/other"}}\n',
            encoding="utf-8",
        )
        os.utime(p, (now - 7200, now - 7200))  # mtime：2 小时前
        assert config_mod._detect_from_rollout("k1", sessions_dir=tmp_path, start_time=now) is None
