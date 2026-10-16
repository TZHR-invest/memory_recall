#!/usr/bin/env python3
"""
LLM 抽取链路健康探针（cron 用，宿主机直接跑）

背景（2026-10-16 事故）：
opencodex 上游 `commandcode` 账号自 10-04 13:36 起额度耗尽，每次调用返回
`HTTP 400 Provider error 400: You have insufficient credits`。后果全静默：
① 实体/关系抽取退回规则抽取（`relations: []` 写死空）⇒ 实体/天 200~685 → 11~27；
② `/extract-memory` 把异常吞成"无值得保存" ⇒ dsh 自动捕获 65~117 条/天 → 0。
两条链路都只留在日志里，看板全绿，**12 天没人发现**（同类 429 事故 09-24~09-26 也静默过）。

本探针补上"人不看日志也能知道"的那一环：
1. **直连探针**：按 apps/api/.env 的 provider 配置发一次最小 chat 请求（1 token）。
2. **落库探针**：查近 1 小时是否有 `metadata._extraction_degraded` 的记忆
   （由 memory_store 在降级时写入，见 src/services/core/llm_entity_extraction.py）。
3. **状态机告警**：ok→fail 立即发邮件；持续失败每 REMIND_HOURS 复提醒一次；
   fail→ok 发恢复通知。状态存 ~/.local/state/memory_recall/llm_probe_state.json。

用法：
    python3 scripts/llm_health_probe.py            # 探一次（cron 默认）
    python3 scripts/llm_health_probe.py --dry-run  # 只打印，不发邮件、不写状态
    python3 scripts/llm_health_probe.py --test-mail  # 发一封测试邮件后退出

cron（宿主机，每 15 分钟）：
    */15 * * * * cd /home/wbaifan/.openclaw/workspace-ai_tui/projects/memory_recall/apps/api && \
        /usr/bin/python3 scripts/llm_health_probe.py >> ~/.memory-recall-llm-probe.log 2>&1
"""

import argparse
import json
import os
import re
import smtplib
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from email.mime.text import MIMEText
from pathlib import Path

HERE = Path(__file__).resolve().parent
API_DIR = HERE.parent
ENV_FILE = API_DIR / ".env"
MAIL_ENV = Path.home() / ".hermes" / "credentials" / "mail.env"
STATE_FILE = Path.home() / ".local" / "state" / "memory_recall" / "llm_probe_state.json"
PG_CONTAINER = "memory_recall-postgres-1"
DB_NAME = "memory_recall"
REMIND_HOURS = 6          # 持续失败时的复提醒间隔
PROBE_TIMEOUT = 30
DEGRADED_LOOKBACK_MIN = 60


def parse_env(path: Path) -> dict:
    out = {}
    if not path.exists():
        return out
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def resolve_provider(env: dict) -> dict:
    """按 LLM_PROVIDER 解析出 (base, key, model)——与 src/llm/client.py 的分支保持一致。"""
    provider = (env.get("LLM_PROVIDER") or "volcengine").lower()
    if provider == "opencodex":
        return {
            "provider": provider,
            "base": env.get("OPENCODEX_API_BASE", "http://192.168.0.206:10100/v1"),
            "key": env.get("OPENCODEX_API_KEY", ""),
            "model": env.get("OPENCODEX_LLM_MODEL", ""),
        }
    if provider == "deepseek":
        return {
            "provider": provider,
            "base": env.get("DEEPSEEK_API_BASE", "https://api.deepseek.com"),
            "key": env.get("DEEPSEEK_API_KEY", ""),
            "model": env.get("DEEPSEEK_LLM_MODEL", "deepseek-v4-flash"),
        }
    return {
        "provider": provider,
        "base": env.get("VOLC_API_BASE", "https://ark.cn-beijing.volces.com/api/v3"),
        "key": env.get("VOLC_API_KEY", ""),
        "model": env.get("VOLC_LLM_MODEL", ""),
    }


def probe_llm(cfg: dict) -> tuple:
    """发一次最小 chat 请求。返回 (ok, detail)。"""
    if not cfg["key"]:
        return False, f"{cfg['provider']} 未配置 API key"
    url = cfg["base"].rstrip("/") + "/chat/completions"
    body = json.dumps({
        "model": cfg["model"],
        "messages": [{"role": "user", "content": "ping"}],
        "max_tokens": 8,
    }).encode()
    req = urllib.request.Request(
        url, data=body, method="POST",
        headers={"Authorization": f"Bearer {cfg['key']}", "Content-Type": "application/json"},
    )
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=PROBE_TIMEOUT) as resp:
            resp.read(200)
            return True, f"HTTP {resp.status}（{time.time() - t0:.1f}s）"
    except urllib.error.HTTPError as e:
        detail = e.read(400).decode(errors="replace")
        msg = re.search(r"'message':\s*'([^']{0,200})", detail) or re.search(r'"message":\s*"([^"]{0,200})', detail)
        why = msg.group(1) if msg else detail[:160].replace("\n", " ")
        if "insufficient credits" in detail:
            why = "额度耗尽（insufficient credits）：" + why
        elif e.code == 429:
            why = "被限流（429）：" + why
        return False, f"HTTP {e.code} {why}"
    except Exception as e:  # noqa: BLE001 — 探针要把任何异常都当成"不健康"
        return False, f"{type(e).__name__}: {e}"


def probe_degraded_memories(lookback_min: int = DEGRADED_LOOKBACK_MIN) -> tuple:
    """查近 N 分钟写入的降级记忆条数（走 docker exec，不需要库密码）。返回 (count|None, detail)。"""
    sql = (
        "SELECT count(*) FROM memories WHERE metadata ? '_extraction_degraded' "
        f"AND created_at >= NOW() - INTERVAL '{int(lookback_min)} minutes'"
    )
    try:
        out = subprocess.run(
            ["docker", "exec", PG_CONTAINER, "psql", "-U", "postgres", "-d", DB_NAME, "-tAc", sql],
            capture_output=True, text=True, timeout=30,
        )
        if out.returncode != 0:
            return None, f"psql 失败: {out.stderr.strip()[:160]}"
        return int(out.stdout.strip() or 0), "ok"
    except Exception as e:  # noqa: BLE001
        return None, f"{type(e).__name__}: {e}"


def send_mail(subject: str, body: str) -> tuple:
    env = parse_env(MAIL_ENV)
    host = env.get("MAIL_SMTP_HOST")
    port = int(env.get("MAIL_SMTP_PORT") or 465)
    user = env.get("MAIL_USER")
    pwd = env.get("MAIL_PASS")
    to = env.get("RECEIVER_EMAIL") or user
    if not (host and user and pwd and to):
        return False, f"邮件凭据不完整（{MAIL_ENV}）"
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = to
    try:
        ctx = ssl.create_default_context()
        with smtplib.SMTP_SSL(host, port, context=ctx, timeout=30) as s:
            s.login(user, pwd)
            s.sendmail(user, [to], msg.as_string())
        return True, f"已发送 → {to}"
    except Exception as e:  # noqa: BLE001
        return False, f"发送失败 {type(e).__name__}: {e}"


def load_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text())
    except Exception:  # noqa: BLE001
        return {}


def save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2))


def main() -> int:
    ap = argparse.ArgumentParser(description="LLM 抽取链路健康探针")
    ap.add_argument("--dry-run", action="store_true", help="只打印，不发邮件/不写状态")
    ap.add_argument("--test-mail", action="store_true", help="发一封测试邮件后退出")
    ap.add_argument("--lookback-min", type=int, default=DEGRADED_LOOKBACK_MIN,
                    help=f"降级记忆回看窗口（默认 {DEGRADED_LOOKBACK_MIN} 分钟）")
    ap.add_argument("--model", help="临时覆盖模型 id（用于验证告警通道/预检候选线路）")
    args = ap.parse_args()

    if args.test_mail:
        ok, detail = send_mail(
            "【测试】memory_recall LLM 探针邮件通道",
            "这是一封测试邮件：收到即表示模型故障告警通道可用。\n"
            f"时间：{datetime.now():%Y-%m-%d %H:%M:%S}",
        )
        print(("✅ " if ok else "❌ ") + detail)
        return 0 if ok else 1

    env = parse_env(ENV_FILE)
    cfg = resolve_provider(env)
    if args.model:
        cfg["model"] = args.model
    llm_ok, llm_detail = probe_llm(cfg)
    deg_count, deg_detail = probe_degraded_memories(args.lookback_min)

    # 判定：直连失败 ⇒ 故障；直连通但近 1h 有降级落库 ⇒ 也算故障（部分失败/别的调用方）
    degraded_by_db = bool(deg_count) if deg_count is not None else False
    healthy = llm_ok and not degraded_by_db
    reasons = []
    if not llm_ok:
        reasons.append(f"直连探针失败：{llm_detail}")
    if degraded_by_db:
        reasons.append(f"近 {args.lookback_min} 分钟有 {deg_count} 条记忆走了降级抽取（规则兜底）")
    if deg_count is None:
        reasons.append(f"降级计数不可用：{deg_detail}")

    now = datetime.now()
    icon = "✅" if healthy else "🔴"
    print(f"{icon} [{now:%Y-%m-%d %H:%M:%S}] provider={cfg['provider']} model={cfg['model']}")
    print(f"   直连探针：{'OK ' + llm_detail if llm_ok else 'FAIL ' + llm_detail}")
    print(f"   降级落库：{deg_count if deg_count is not None else '未知'}（近 {args.lookback_min} 分钟）")

    if args.dry_run:
        print("（dry-run：不发邮件、不写状态）")
        return 0

    state = load_state()
    prev = state.get("status")            # "ok" / "fail" / None
    last_mail_ts = state.get("last_mail_ts", 0)
    should_mail, subject, body = False, "", ""

    if not healthy:
        first_fail = prev != "fail"
        due_remind = (time.time() - last_mail_ts) >= REMIND_HOURS * 3600
        if first_fail or due_remind:
            should_mail = True
            subject = f"🔴 memory_recall LLM 抽取链路故障（{cfg['provider']}/{cfg['model']}）"
            body = (
                "memory_recall 的 LLM 抽取链路探针判定为**故障**。\n\n"
                + "\n".join(f"- {r}" for r in reasons) + "\n\n"
                "影响面（2026-10-16 事故实测）：\n"
                "① 新记忆的实体/关系退回规则抽取（关系恒为空）⇒ 图谱召回对该批记忆失效；\n"
                "② dsh 自动捕获蒸馏失败 ⇒ 对话内容不再落库（插件回退 raw 前的内容会丢）。\n\n"
                f"排查：`cd {API_DIR} && python3 scripts/llm_health_probe.py --dry-run`；"
                f"`docker logs --tail 200 memory_recall-api-1 | grep -E '降级|insufficient'`\n"
                f"处置：给 {cfg['provider']} 上游充值，或改 .env 的 OPENCODEX_LLM_MODEL 换可用线路后 "
                "`docker compose up -d api`。\n\n"
                f"时间：{now:%Y-%m-%d %H:%M:%S}\n"
                f"（持续故障每 {REMIND_HOURS} 小时复提醒一次；恢复会另发一封）"
            )
    elif prev == "fail":
        should_mail = True
        subject = f"🟢 memory_recall LLM 抽取链路已恢复（{cfg['provider']}/{cfg['model']}）"
        body = (
            "探针判定已恢复：\n\n"
            f"- 直连探针：{llm_detail}\n"
            f"- 近 {args.lookback_min} 分钟降级记忆：{deg_count}\n\n"
            "提醒：故障期间写入的记忆实体/关系是规则兜底结果，建议跑回填：\n"
            f"  cd {API_DIR} && python3 scripts/backfill_entities.py --since 2026-10-04 --dry-run\n\n"
            f"时间：{now:%Y-%m-%d %H:%M:%S}"
        )

    if should_mail:
        ok, detail = send_mail(subject, body)
        print(("   📧 " + detail) if ok else ("   ⚠️ 邮件未发出：" + detail))
        if ok:
            state["last_mail_ts"] = time.time()

    state["status"] = "ok" if healthy else "fail"
    state["last_check"] = now.isoformat()
    state["last_detail"] = llm_detail
    state["last_degraded_60m"] = deg_count
    save_state(state)
    return 0 if healthy else 2


if __name__ == "__main__":
    sys.exit(main())
