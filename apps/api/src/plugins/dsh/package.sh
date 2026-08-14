#!/bin/bash
# package.sh — memory-recall-dsh 一键分发打包
#
# 生成自包含安装包 dist/memory-recall-dsh-install.tar.gz：
#   - 插件运行文件（package.json + *.js + build-bundle.mjs + install.sh）
#   - 契约预检 preflight.mjs 副本（安装包自包含，目标机器无需 dsh-plugins 仓库）
#   - 安装说明 README.INSTALL.md
#
# 用法:
#   bash package.sh                          # 生成自包含安装包（版本取 package.json）
#   bash package.sh --version 1.1.0          # 覆盖版本号
#
# 后端地址不在打包时写死：memory-recall 后端是各用户自部署的远程服务器，
# 地址由目标机器安装时配置（install.sh --backend-url / MEMORY_RECALL_BASE_URL /
# 交互询问）。
#
# 其他机器安装（三步）:
#   1. scp dist/memory-recall-dsh-install.tar.gz user@目标机:~/
#   2. cd ~ && tar xzf memory-recall-dsh-install.tar.gz && cd memory-recall-dsh-install
#   3. bash install.sh --api-key rk_live_xxx --backend-url http://<你的服务器>:8000
#      # 不传 --backend-url 时会交互询问（默认 http://localhost:8000）
#      # 激活：bash install.sh --restart（终端执行；冒烟通过才重启，插件问题自动中止）
set -u

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"          # apps/api
VERSION=""
while [ $# -gt 0 ]; do
  case "$1" in
    --version=*) VERSION="${1#--version=}" ;;
    --version) VERSION="$2"; shift ;;
    *) echo "未知参数: $1"; exit 1 ;;
  esac
  shift
done

DIST="$HERE/dist"
STAGE="$DIST/stage"
rm -rf "$STAGE"
mkdir -p "$STAGE"

# 插件文件
for f in package.json index.js config.js client-lib.js client.js context.js tools.js capture.js install.sh build-bundle.mjs; do
  [ -f "$HERE/$f" ] || { echo "错误：缺少 $HERE/$f"; exit 1; }
done
cp "$HERE"/package.json "$HERE"/index.js "$HERE"/config.js "$HERE"/client-lib.js \
   "$HERE"/client.js "$HERE"/context.js "$HERE"/tools.js "$HERE"/capture.js \
   "$HERE"/install.sh "$HERE"/build-bundle.mjs "$STAGE/"

# 契约预检副本（自包含，目标机器无需 dsh-plugins 仓库）
if [ -f "$REPO/../dsh-plugins/scripts/preflight.mjs" ]; then
  cp "$REPO/../dsh-plugins/scripts/preflight.mjs" "$STAGE/preflight.mjs"
elif [ -f "$HOME/dsh-plugins/scripts/preflight.mjs" ]; then
  cp "$HOME/dsh-plugins/scripts/preflight.mjs" "$STAGE/preflight.mjs"
else
  echo "[警告] 未找到 dsh-plugins/scripts/preflight.mjs，安装包将不带契约预检（install.sh 会跳过预检）"
fi

# 版本号覆盖
if [ -n "$VERSION" ]; then
  node -e "
const fs=require('fs');
const p='$STAGE/package.json';
const j=JSON.parse(fs.readFileSync(p,'utf8'));
j.version='$VERSION';
fs.writeFileSync(p,JSON.stringify(j,null,2)+'\n');
" || { echo "[警告] 版本覆盖失败（用 package.json 原版本）"; }
fi
PKG_VERSION=$(node -e "console.log(require('$STAGE/package.json').version)")

# 安装说明
cat > "$STAGE/README.INSTALL.md" <<MDEOF
# memory-recall-dsh 一键安装（版本 $PKG_VERSION）

后端地址：**由你安装时配置**（memory-recall 后端是你自部署的服务器，地址不固定）。
配置优先级：install.sh --backend-url 参数 > 环境变量 MEMORY_RECALL_BASE_URL > 交互询问（默认 http://localhost:8000）。

## 安装（目标机器，需已安装并运行过 dsh web）

1. 解压: tar xzf memory-recall-dsh-install.tar.gz && cd memory-recall-dsh-install
2. 安装:
   bash install.sh --api-key rk_live_xxx --backend-url http://<你的后端服务器>:8000
   （API Key 来自 memory-recall 后端，rk_live_/rk_test_ 开头；也可用环境变量
     MEMORY_RECALL_API_KEY / MEMORY_RECALL_BASE_URL；不传 --backend-url 会交互询问）
3. 激活: bash install.sh --restart   # 终端执行！内置契约预检 + headless 冒烟，
                                     # 插件有问题自动中止，不会让 dsh 启动即崩
4. 验证: 页面 200；/plugins/memory-recall-dsh/client.js 返回 200；新会话注入召回上下文

## 其他命令

- bash install.sh --check     # 只检查状态（含契约预检）
- bash install.sh --smoke     # 只跑 headless 试启动冒烟
- bash install.sh --uninstall # 卸载回滚

## 要求

- Node.js 18.17+；dsh 已初始化（~/.dsh/profiles/web 存在）
- memory-recall 后端可达（默认 $BACKEND_URL）
- headless 冒烟需要 dsh headless profile（首次运行 dsh --profile headless "1" 自动初始化）
MDEOF

# 打包（包内顶层目录名 = memory-recall-dsh-install，解压后 cd 即用）
mv "$DIST/stage" "$DIST/memory-recall-dsh-install"
tar czf "$DIST/memory-recall-dsh-install.tar.gz" -C "$DIST" memory-recall-dsh-install
echo "== 打包完成 =="
echo "  产物: $DIST/memory-recall-dsh-install.tar.gz"
echo "  解压目录: $DIST/memory-recall-dsh-install/"
echo "  版本: $PKG_VERSION（后端地址由目标机器安装时配置）"
echo "  内容: $(ls "$DIST/memory-recall-dsh-install" | tr '\n' ' ')"
