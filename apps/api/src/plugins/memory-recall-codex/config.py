
"""Memory Recall Codex 插件配置加载（仅依赖标准库，可独立单测）。

配置优先级：环境变量 > ~/.config/codex/memory-recall.jsonc > 默认值
"""

import json
import logging
import os
import re
import time
from pathlib import Path

logger = logging.getLogger("memory-recall-codex-config")


def strip_jsonc_comments(content: str) -> str:
    """字符串感知的 JSONC 注释剥离。

    不会误伤字符串内的 `//`（如 `http://localhost:8000`）、转义序列与 `/* */` 注释，
    并去掉对象/数组末尾的逗号。
    """
    out = []
    in_string = False
    i = 0
    n = len(content)
    while i < n:
        c = content[i]
        if in_string:
            out.append(c)
            if c == '\\' and i + 1 < n:
                out.append(content[i + 1])
                i += 2
                continue
            if c == '"':
                in_string = False
            i += 1
            continue
        if c == '"':
            in_string = True
            out.append(c)
            i += 1
            continue
        if c == '/' and i + 1 < n:
            nxt = content[i + 1]
            if nxt == '/':
                while i < n and content[i] != '\n':
                    i += 1
                continue
            if nxt == '*':
                i += 2
                while i + 1 < n and not (content[i] == '*' and content[i + 1] == '/'):
                    i += 1
                i += 2
                continue
        out.append(c)
        i += 1
    stripped = ''.join(out)
    return re.sub(r',(\s*[}\]])', r'\1', stripped)


def load_config(config_path: Path | None = None) -> dict:
    """加载配置：默认值 <- 配置文件 <- 环境变量（后者优先）。
    """
    cfg = {
        "base_url": "http://localhost:8000", "api_key": "",
        "user_tag": "codex-user", "project_tag": "codex-default",
        "max_memories": 10, "max_chunks": 5, "similarity_threshold": 0.3,
        "enable_graph_recall": True, "enable_entity_recall": True,
        "graph_max_depth": 2, "graph_max_nodes": 5,
    }
    config_path = config_path or (Path.home() / ".config" / "codex" / "memory-recall.jsonc")
    if config_path.exists():
        try:
            raw = config_path.read_text(encoding="utf-8")
            clean = strip_jsonc_comments(raw)
            file_cfg = json.loads(clean)
            cfg.update({k: v for k, v in file_cfg.items() if v not in (None, "")})
        except Exception as e:
            logger.warning(f"Failed to parse {config_path}: {e}")
    for env_key, cfg_key in {
        "MEMORY_RECALL_BASE_URL": "base_url", "MEMORY_RECALL_API_KEY": "api_key",
        "MEMORY_RECALL_USER_TAG": "user_tag", "MEMORY_RECALL_PROJECT_TAG": "project_tag",
    }.items():
        if os.environ.get(env_key):
            cfg[cfg_key] = os.environ[env_key]
    # project_tag 未显式指定（空/auto/默认占位）时自动探测；
    # 探测失败统一回退 codex-default（不能把 "auto" 本身当 fallback 回填）
    if not cfg["project_tag"] or cfg["project_tag"] in ("auto", "codex-default"):
        cfg["project_tag"] = detect_project_tag(cfg["user_tag"], fallback="codex-default")
    return cfg


def _read_cmdline(pid: int) -> str:
    """读取 /proc/<pid>/cmdline（不存在/无权限返回空串）。"""
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as f:
            return f.read().decode(errors="ignore").replace("\x00", " ")
    except OSError:
        return ""


def _is_codex_cli_parent(cmdline: str) -> bool:
    """判断父进程是否为 codex CLI（而非路径含 codex 的其他进程）。

    用 argv[0] 的可执行文件名判定（codex / codex.exe / codex-*），避免
    "codex" 子串误伤：venv 路径（~/.config/codex/...）、opencodex 等
    进程名或路径含 codex 但并非 codex CLI 的情况。
    """
    parts = cmdline.split()
    if not parts:
        return False
    base = Path(parts[0]).name
    if not (base == "codex" or base.startswith("codex.") or base.startswith("codex-")):
        return False
    # VSCode 扩展宿主（app-server / code-mode-host）不是 CLI
    if "app-server" in cmdline or "code-mode-host" in cmdline:
        return False
    return True


def _detect_from_parent(user_tag: str) -> str | None:
    """父进程为 codex CLI 时按其 cwd 生成 tag；否则返回 None。"""
    try:
        ppid = os.getppid()
        cmdline = _read_cmdline(ppid)
        if not _is_codex_cli_parent(cmdline):
            return None
        return _tag_from_cwd(user_tag, os.readlink(f"/proc/{ppid}/cwd"))
    except OSError:
        return None


def detect_project_tag(user_tag: str, fallback: str = "codex-default") -> str:
    """project_tag 自动探测：父进程 cwd（CLI）> rollout 会话记录（VSCode）> fallback。

    探测不到可靠的项目目录时直接回退 fallback（codex-default），绝不写入
    插件自身仓库之类的无关容器，避免污染其他项目的记忆。"""
    return (
        _detect_from_parent(user_tag)
        or _detect_from_rollout(user_tag)
        or fallback
    )

_ROLLOUT_RE = re.compile(r"rollout-(\d{4})-(\d{2})-(\d{2})T(\d{2})-(\d{2})-(\d{2})-")

def _rollout_cwd_from_file(path: Path) -> str | None:
    """读 rollout 首行 session_meta 的 cwd（损坏/无字段返回 None）。"""
    try:
        with path.open(encoding="utf-8", errors="ignore") as f:
            line = f.readline().strip()
        if not line.startswith("{"):
            return None
        data = json.loads(line)
        cwd = (data.get("payload") or {}).get("cwd")
        return cwd if isinstance(cwd, str) and cwd else None
    except Exception:
        return None

def _tag_from_cwd(user_tag: str, cwd: str | None) -> str | None:
    """校验 cwd 合理性并生成 {user_tag}_project-<目录名>；无效返回 None。

    仅过滤 home、/tmp、~/.vscode* 等非项目目录；隐藏目录（如 .codex）保留
    原名生成独立容器，避免误并入其他项目容器。"""
    home = str(Path.home())
    if (
        not cwd
        or cwd in (home, "/")
        or cwd.startswith("/tmp")
        or cwd.startswith(home + "/.vscode")
    ):
        return None
    name = Path(cwd).name
    if not name:
        return None
    return f"{user_tag}_project-{name}"

def _detect_from_rollout(
    user_tag: str, sessions_dir: Path | None = None, start_time: float | None = None
) -> str | None:
    """从 codex 会话 rollout 文件（~/.codex/sessions/**/rollout-*.jsonl）匹配当前会话。

    codex 把每个会话的 cwd 写进 rollout 首行 session_meta；MCP server 由 codex
    在会话创建时拉起（实测与 rollout 文件时间戳同秒），故取与进程启动时间最接近
    的 rollout（时间窗 5 分钟内）即可定位当前项目目录。
    适用于 VSCode 扩展模式（父进程无 cwd 信息）。"""
    sessions_dir = sessions_dir or (Path.home() / ".codex" / "sessions")
    start_time = start_time if start_time is not None else _START_TIME
    if not sessions_dir.is_dir():
        return None
    # 1) 按文件名时间戳匹配（新会话场景：server 拉起时刻 ≈ 会话创建时刻）
    best: tuple[float, Path] | None = None
    try:
        for p in sessions_dir.rglob("rollout-*.jsonl"):
            m = _ROLLOUT_RE.search(p.name)
            if not m:
                continue
            try:
                ts = time.mktime(tuple(int(x) for x in m.groups()) + (0, 0, -1))
            except (ValueError, OverflowError):
                continue
            diff = abs(ts - start_time)
            if diff > 300:
                continue  # 超出时间窗：旧会话/重启场景，进入 mtime 兜底
            if best is None or diff < best[0]:
                best = (diff, p)
    except OSError:
        return None
    if best is not None:
        tag = _tag_from_cwd(user_tag, _rollout_cwd_from_file(best[1]))
        if tag:
            return tag
    # 2) mtime 兜底（长会话 + server 重启场景：活跃会话的 rollout 持续写入，
    #    文件修改时间新鲜，按 mtime 取最新且 10 分钟窗口内的 rollout）
    try:
        recent = [
            p for p in sessions_dir.rglob("rollout-*.jsonl")
            if abs(p.stat().st_mtime - start_time) <= 600
        ]
    except OSError:
        return None
    if recent:
        newest = max(recent, key=lambda p: p.stat().st_mtime)
        return _tag_from_cwd(user_tag, _rollout_cwd_from_file(newest))
    return None

_START_TIME = time.time()  # 模块导入时刻 ≈ MCP server 进程启动时刻


CONFIG = load_config()
API_BASE_URL, API_KEY = CONFIG["base_url"], CONFIG["api_key"]
USER_TAG, PROJECT_TAG = CONFIG["user_tag"], CONFIG["project_tag"]


_PROJECT_TAG_FALLBACK = "codex-default"


def ensure_project_tag() -> str:
    """项目容器启动竞态兜底（VSCode 扩展模式）。

    MCP server 与 codex 会话 rollout 文件几乎同时创建：若 server 的模块导入
    先于 rollout 落盘，启动探测会回退 codex-default 并被冻结，导致 project
    范围所有请求 403（容器前缀不匹配 API Key）。首次使用工具时重新探测一次
    （此时 rollout 通常已存在）；仍未成功则保持回退值，下次调用再试，直到成功。
    """
    global PROJECT_TAG
    if PROJECT_TAG == _PROJECT_TAG_FALLBACK:
        detected = detect_project_tag(USER_TAG)
        if detected and detected != _PROJECT_TAG_FALLBACK:
            logger.info(
                "项目容器启动探测回退 %r，首次使用重探测为 %r",
                _PROJECT_TAG_FALLBACK, detected,
            )
            PROJECT_TAG = detected
    return PROJECT_TAG
