#!/bin/bash
# install.sh — memory-recall-dsh 一键安装 / 检查 / 卸载
#
# 把本插件装进 dsh（DeepSeek Harness）：
#   1. 源码复制到 $DSH_HOME/plugins/memory-recall-dsh/（留档）
#   2. 运行副本复制到 $DSH_HOME/profiles/node_modules/memory-recall-dsh/（loader 解析）
#   3. 目标 profile 的 cordis.patch.yml 追加 insert 接线（幂等）
#
# 用法:
#   bash install.sh                       # 安装到 web profile（幂等，可反复执行）
#   bash install.sh --profile headless    # 安装到其他 profile
#   bash install.sh --api-key rk_live_xxx # 把 API Key 写进 patch config（可选；不写则运行时读 MEMORY_RECALL_API_KEY）
#   bash install.sh --check               # 只检查状态，不改任何文件
#   bash install.sh --smoke               # 只跑 headless 试启动冒烟（隔离环境，不动正式 web）
#   bash install.sh --restart             # 冒烟通过后重启 dsh web 并验证（会中断当前 web 服务几秒）
#   bash install.sh --uninstall           # 卸载（移除接线与安装副本）
#
# 环境变量: DSH_HOME（默认 ~/.dsh）、MEMORY_RECALL_API_KEY、MEMORY_RECALL_BASE_URL
set -u

# 比较插件全部关键文件（package.json + 所有 .js），任一变化都需要重装
FILES_IDENTICAL() {
  local src="$1" dst="$2"
  for f in "$src"/*.js; do
    [ -f "$f" ] || continue
    local base
    base="$(basename "$f")"
    [ -f "$dst/$base" ] || return 1
    diff -q "$f" "$dst/$base" >/dev/null 2>&1 || return 1
  done
  diff -q "$src/package.json" "$dst/package.json" >/dev/null 2>&1 || return 1
  return 0
}

MODE="apply"
PROFILE="web"
API_KEY=""
BACKEND_URL=""

i=0
ARGS=("$@")
while [ $i -lt ${#ARGS[@]} ]; do
  arg="${ARGS[$i]}"
  case "$arg" in
    --check) MODE="check" ;;
    --restart) MODE="restart" ;;
    --smoke) MODE="smoke" ;;
    --uninstall) MODE="uninstall" ;;
    --profile=*) PROFILE="${arg#--profile=}" ;;
    --api-key=*) API_KEY="${arg#--api-key=}" ;;
    --backend-url=*) BACKEND_URL="${arg#--backend-url=}" ;;
    --profile)
      i=$((i + 1))
      [ $i -lt ${#ARGS[@]} ] || { echo "用法: --profile <name>"; exit 1; }
      PROFILE="${ARGS[$i]}"
      ;;
    --api-key)
      i=$((i + 1))
      [ $i -lt ${#ARGS[@]} ] || { echo "用法: --api-key <key>"; exit 1; }
      API_KEY="${ARGS[$i]}"
      ;;
    --backend-url)
      i=$((i + 1))
      [ $i -lt ${#ARGS[@]} ] || { echo "用法: --backend-url <url>"; exit 1; }
      BACKEND_URL="${ARGS[$i]}"
      ;;
    --*) echo "未知参数: $arg"; exit 1 ;;
  esac
  i=$((i + 1))
done

# 后端地址解析：--backend-url > MEMORY_RECALL_BASE_URL > 交互询问（仅 apply 且终端）> 默认。
# 后端是各用户自部署的远程服务器，地址不固定，安装时由用户配置。
resolve_backend_url() {
  if [ -n "$BACKEND_URL" ]; then echo "$BACKEND_URL"; return; fi
  if [ -n "${MEMORY_RECALL_BASE_URL:-}" ]; then echo "$MEMORY_RECALL_BASE_URL"; return; fi
  if [ "$MODE" = "apply" ] && [ -t 0 ]; then
    printf "memory-recall 后端地址（默认 http://localhost:8000；自部署远程服务器如 http://<IP>:8000）: "
    stty -echo 2>/dev/null || true   # 关回显，避免 pty 下提示文本被 read 吞入
    read -r INPUT_URL || true
    stty echo 2>/dev/null || true
    echo ""
    echo "${INPUT_URL:-http://localhost:8000}"
    return
  fi
  echo "http://localhost:8000"
}
# API Key 解析：--api-key > MEMORY_RECALL_API_KEY > 交互询问（仅 apply 且终端）> 留空（运行时 env 兜底）
resolve_api_key() {
  if [ -n "$API_KEY" ]; then echo "$API_KEY"; return; fi
  if [ -n "${MEMORY_RECALL_API_KEY:-}" ]; then echo "$MEMORY_RECALL_API_KEY"; return; fi
  if [ "$MODE" = "apply" ] && [ -t 0 ]; then
    printf "memory-recall API Key（可留空，运行时读环境变量 MEMORY_RECALL_API_KEY；输入不回显）: "
    stty -echo 2>/dev/null || true   # 敏感信息不回显
    read -r INPUT_KEY || true
    stty echo 2>/dev/null || true
    echo ""
    echo "${INPUT_KEY:-}"
    return
  fi
  echo ""
}

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DSH="${DSH_HOME:-$HOME/.dsh}"
SRC="$HERE"
DST_PLUGINS="$DSH/plugins/memory-recall-dsh"
DST_PROFILE="$DSH/profiles/node_modules/memory-recall-dsh"
PATCH="$DSH/profiles/$PROFILE/cordis.patch.yml"
PLUGIN_ID="memory-recall-dsh"
PLUGIN_NAME="memory-recall-dsh"
FAIL=0

echo "== memory-recall-dsh 安装（mode: $MODE, profile: $PROFILE）=="
echo "  DSH 目录: $DSH"
echo "  源码目录: $SRC"

# ── 0/4 前置检查 ──────────────────────────────────────────────────────────
echo "== 0/4 前置检查 =="
for f in package.json index.js config.js client.js client-lib.js context.js tools.js capture.js; do
  if [ ! -f "$SRC/$f" ]; then
    echo "  错误：缺少 $SRC/$f（安装包不完整）"; exit 1
  fi
done
for f in "$SRC"/*.js; do
  [ -f "$f" ] || continue
  node --check "$f" >/dev/null 2>&1 || { echo "  错误：语法检查失败 $f"; FAIL=1; }
done
[ "$FAIL" = "1" ] && exit 1
echo "  [OK] 插件源码完整，语法检查通过"

# 契约预检（防 MR-022/023 重演）：dsh.client.platform / exports["./client"] / classic-script bundle
# 预检脚本探测顺序：安装包内（分发 tarball 自带，自包含）> DSH_PLUGINS_REPO >
# ~/dsh-plugins；缺失时跳过（本插件自带测试已覆盖契约）
PREFLIGHT=""
for CAND in "$HERE/preflight.mjs" "${DSH_PLUGINS_REPO:-$HOME/dsh-plugins}/scripts/preflight.mjs"; do
  [ -n "$CAND" ] && [ -f "$CAND" ] && PREFLIGHT="$CAND" && break
done
echo "== 0.5/4 契约预检（${PREFLIGHT:-未找到 dsh-plugins/preflight.mjs}）=="
if [ -n "$PREFLIGHT" ]; then
  if node "$PREFLIGHT" "$SRC"; then
    echo "  [OK] 加载器契约检查通过"
  else
    if [ "$MODE" = "check" ]; then
      FAIL=1
    else
      echo "  [错误] 契约预检未通过——安装会破坏 dsh 启动，已中止。请修复后重试。"
      exit 1
    fi
  fi
else
  echo "  [跳过] 未找到共享 preflight.mjs（可安装 dsh-plugins 仓库或设置 DSH_PLUGINS_REPO）"
fi

if [ ! -d "$DSH/profiles/$PROFILE" ]; then
  echo "  [跳过] profile '$PROFILE' 尚未初始化（$DSH/profiles/$PROFILE 不存在）"
  echo "         请先运行一次 dsh $PROFILE 完成初始化，再重跑本脚本接线"
  exit 1
fi
[ -d "$DSH/profiles/node_modules" ] || { echo "  错误：$DSH/profiles/node_modules 不存在，请确认 dsh 已运行过"; exit 1; }

# ── 1/4 复制源码到 plugins/（留档） ───────────────────────────────────────
echo "== 1/4 源码留档 =="
if [ -f "$DST_PLUGINS/index.js" ] && FILES_IDENTICAL "$SRC" "$DST_PLUGINS"; then
  echo "  [已有] $DST_PLUGINS（内容一致）"
else
  if [ "$MODE" = "check" ]; then
    echo "  [缺失/不同] $DST_PLUGINS"
    FAIL=1
  else
    mkdir -p "$DST_PLUGINS"
    cp "$SRC"/package.json "$SRC"/*.js "$DST_PLUGINS/"
    echo "  [已装] $DST_PLUGINS"
  fi
fi

# ── 2/4 复制运行副本到 profiles/node_modules/ ─────────────────────────────
echo "== 2/4 运行副本 =="
if [ -f "$DST_PROFILE/index.js" ] && FILES_IDENTICAL "$SRC" "$DST_PROFILE"; then
  echo "  [已有] $DST_PROFILE（内容一致）"
else
  if [ "$MODE" = "check" ]; then
    echo "  [缺失/不同] $DST_PROFILE"
    FAIL=1
  else
    mkdir -p "$DST_PROFILE"
    cp "$SRC"/package.json "$SRC"/*.js "$DST_PROFILE/"
    echo "  [已装] $DST_PROFILE"
  fi
fi

# ── 3/4 profile patch 接线 ────────────────────────────────────────────────
echo "== 3/4 组合接线（$PATCH）=="
if [ -f "$PATCH" ] && grep -q "memory-recall-dsh" "$PATCH" 2>/dev/null; then
  echo "  [已有] $PATCH 中的 memory-recall-dsh 接线"
elif [ "$MODE" = "check" ]; then
  echo "  [缺失] $PATCH 中的 memory-recall-dsh 接线"
  FAIL=1
else
  mkdir -p "$(dirname "$PATCH")"
  # 模板补丁默认内容是裸 `[]`，追加前先移除，避免 YAML 双文档语法错误
  if [ -f "$PATCH" ] && grep -q '^\[\]$' "$PATCH" 2>/dev/null; then
    sed -i '/^\[\]$/d' "$PATCH"
  fi
  BACKEND_URL="$(resolve_backend_url)"
  API_KEY="$(resolve_api_key)"
  cat >> "$PATCH" <<PATCHEOF

# memory-recall-dsh：长期记忆插件（工具 + 自动召回 + 自动捕获）。
# 后端地址/API Key 由安装时配置；也可用环境变量 MEMORY_RECALL_API_KEY / MEMORY_RECALL_BASE_URL。
- insert:
    - id: memory-recall-dsh
      name: 'memory-recall-dsh'
      config:
        apiKey: '$API_KEY'
        baseUrl: '$BACKEND_URL'
PATCHEOF
  echo "  [已加] $PATCH（baseUrl=$BACKEND_URL；apiKey: ${API_KEY:+已写入}${API_KEY:-未写入，运行时读环境变量}）"
fi

# ── 定位 dsh 安装根 ───────────────────────────────────────────────────────
ROOT=""
for d in $(ls -dt "$HOME"/.npm/_npx/*/ 2>/dev/null); do
  d=${d%/}
  [ -d "$d/node_modules/@deepseek-ai" ] || continue
  ROOT="$d"
  break
done

# ── headless 试启动冒烟（隔离环境验证插件组合，防"启动即崩"）──────────────
# 组合有问题（如 client-modules 契约错误）时 headless 在 boot 阶段即崩溃退出，
# 命中插件关键字则判定为插件问题并中止正式重启；未命中（LLM/网络类）只警告。
SMOKE_LOG=/tmp/mr-dsh-smoke.log
SMOKE_TEST() {
  local dsh_bin="$1"
  echo "== 冒烟：headless 试启动（隔离环境，不影响正式 web）=="
  if [ ! -d "$DSH/profiles/headless" ]; then
    echo "  [跳过] headless profile 未初始化（首次运行 dsh --profile headless 可初始化），冒烟跳过"
    return 0
  fi
  # 确保 headless profile 已接入插件（幂等）
  if [ -f "$DSH/profiles/headless/cordis.patch.yml" ] && grep -q "memory-recall-dsh" "$DSH/profiles/headless/cordis.patch.yml" 2>/dev/null; then
    echo "  [已有] headless 插件接线"
  else
    mkdir -p "$DSH/profiles/headless"
    [ -f "$DSH/profiles/headless/cordis.patch.yml" ] || printf '[]\n' > "$DSH/profiles/headless/cordis.patch.yml"
    sed -i '/^\[\]$/d' "$DSH/profiles/headless/cordis.patch.yml"
    [ -n "$BACKEND_URL" ] || BACKEND_URL="$(resolve_backend_url)"
    cat >> "$DSH/profiles/headless/cordis.patch.yml" <<PATCHEOF

# memory-recall-dsh：长期记忆插件（自动接入，供 headless 冒烟试启动）
- insert:
    - id: memory-recall-dsh
      name: 'memory-recall-dsh'
      config:
        baseUrl: '${BACKEND_URL:-http://localhost:8000}'
PATCHEOF
    echo "  [已接线] headless profile（自动接入，仅用于冒烟）"
  fi
  local start_ts end_ts
  start_ts=$(date +%s)
  if timeout 120 env MEMORY_RECALL_API_KEY="${MEMORY_RECALL_API_KEY:-}" "$dsh_bin" --profile headless "1" > "$SMOKE_LOG" 2>&1; then
    end_ts=$(date +%s)
    echo "  [PASS] headless 试启动成功（$((end_ts - start_ts))s），插件组合无问题"
    return 0
  fi
  end_ts=$(date +%s)
  echo "  [FAIL] headless 试启动失败（$((end_ts - start_ts))s）"
  if grep -qiE "client-modules|plugin tree failed|cannot resolve entry|memory-recall-dsh" "$SMOKE_LOG"; then
    echo "  命中插件组合/加载错误关键字，判定为插件问题："
    grep -iE "client-modules|plugin tree failed|cannot resolve entry|memory-recall-dsh" "$SMOKE_LOG" | head -5
    echo "  完整日志: $SMOKE_LOG"
    echo "  回滚：bash install.sh --uninstall 后重启 dsh web 即可恢复"
    return 1
  fi
  echo "  未命中插件关键字（疑似 LLM/网络类问题，非插件导致），完整日志: $SMOKE_LOG"
  return 2
}

# ── 4/4 冒烟 + 重启（可选）──────────────────────────────────────────────
if [ "$MODE" = "smoke" ] || [ "$MODE" = "restart" ]; then
  if [ -n "$ROOT" ] && [ -x "$ROOT/node_modules/.bin/dsh" ]; then
    SMOKE_TEST "$ROOT/node_modules/.bin/dsh"
    SMOKE_RC=$?
    # smoke 模式：0=通过，1=插件问题，2=非插件问题（LLM/网络等），供 CI/人工判断
    [ "$MODE" = "smoke" ] && exit "$SMOKE_RC"
    # restart：命中插件关键字失败时中止重启，避免正式服务再次启动即崩
    if [ "$SMOKE_RC" = "1" ]; then
      echo "  [中止] 冒烟判定插件有问题，不重启 dsh web（正式服务保持当前状态）"
      exit 1
    fi
  else
    echo "  [警告] 无法定位 dsh 可执行文件，冒烟跳过"
  fi
fi

if [ "$MODE" = "restart" ]; then
  echo "== 4/4 重启 dsh web =="
  pkill -TERM -f 'node_modules/.bin/dsh web' 2>/dev/null
  pkill -TERM -f 'npm exec @deepseek-ai/dsh web' 2>/dev/null
  pkill -TERM -f 'sh -c dsh web' 2>/dev/null
  # 实际 cmdline 是 node .../@deepseek-ai/dsh/lib/bin.js web（2026-08-15 实测：旧模式匹配不到，重启失败 EADDRINUSE）
  pkill -TERM -f '@deepseek-ai/dsh/lib/bin.js web' 2>/dev/null
  sleep 3
  if [ -n "$ROOT" ] && [ -x "$ROOT/node_modules/.bin/dsh" ]; then
    cd "$ROOT" || exit 1
    setsid nohup ./node_modules/.bin/dsh web >> /tmp/dsh-web.log 2>&1 < /dev/null &
    echo "  新进程 PID=$!"
    sleep 8
    curl -s -o /dev/null -w "  127.0.0.1:3080 页面 -> %{http_code}\n" http://127.0.0.1:3080/ || echo "  [警告] 页面未就绪，请稍后手动刷新"
    curl -s -o /dev/null -w "  memory-recall-dsh bundle -> %{http_code}\n" http://127.0.0.1:3080/plugins/memory-recall-dsh/client.js
  else
    echo "  [警告] 无法定位 dsh 可执行文件，请手动重启 dsh web"
  fi
fi

# ── 卸载 ──────────────────────────────────────────────────────────────────
if [ "$MODE" = "uninstall" ]; then
  echo "== 卸载 =="
  if [ -f "$PATCH" ]; then
    python3 - "$PATCH" <<'PYEOF' 2>/dev/null || sed -i '/memory-recall-dsh/d' "$PATCH"
import sys, re
p = sys.argv[1]
text = open(p, encoding="utf-8").read()
# 移除从注释行到 insert 块结束（以 "- insert:" 开头的块）——简化处理：删除含 memory-recall-dsh 的注释与条目
lines = text.splitlines(keepends=True)
out, skip = [], False
for i, ln in enumerate(lines):
    if "memory-recall-dsh" in ln:
        skip = True
        continue
    if skip and (ln.strip().startswith("- id:") or ln.strip().startswith("#") or not ln.strip()):
        skip = False
    if not skip:
        out.append(ln)
open(p, "w", encoding="utf-8").write("".join(out))
PYEOF
    echo "  [已清] $PATCH 中的接线"
  fi
  rm -rf "$DST_PROFILE" "$DST_PLUGINS"
  echo "  [已删] $DST_PROFILE / $DST_PLUGINS"
  echo "  完成。重启 dsh 后插件生效移除。"
  exit 0
fi

if [ "$MODE" = "check" ]; then
  echo "== 检查完成（未改动任何文件）=="
  [ "$FAIL" = "1" ] && echo "（存在缺失项，直接运行 bash install.sh 即可补齐）"
  exit 0
fi

echo "== 完成 =="
echo "  重启 dsh web 后插件生效（bash install.sh --restart 可一键重启验证）。"
