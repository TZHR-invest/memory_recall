/**
 * build-bundle.mjs — 从 client-lib.js（node ESM 库）生成浏览器端 client.js
 *
 * 背景（MR-023）：dsh web 用 script 标签按 classic script 加载插件 bundle，
 * bundle 不能含 import/export（会直接 SyntaxError），且必须顶层调用
 * window.__ModuleLoader__.load({ id, factory }) 注册插件形状
 * { name, inject, apply }——只 export 不注册会报
 * "loaded without registering ... via __ModuleLoader__.load"。
 * host 端固定以 /plugins/<id>/client.js 伺服 exports["./client"] 指向的文件，
 * 所以磁盘上的 bundle 必须叫 client.js。
 *
 * 用法：
 *   node build-bundle.mjs                # 默认用 client-lib.js 生成 client.js
 *   node build-bundle.mjs <src> <dst>    # 指定输入输出
 *
 * 生成产物 client.js 提交进仓库；test/bundle.test.js 保证产物与库同步。
 */

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));

/** 从 ESM 库源码构建 classic-script bundle 文本 */
export function buildClientBundle(libSource) {
  // client-lib.js 的 export 均为内联声明（export function/class），剥掉即可
  const body = libSource.replace(/\bexport\s+/g, "");
  return "/* 本文件由 build-bundle.mjs 从 client-lib.js 自动生成，勿手改；改库后重跑 node build-bundle.mjs */\n" +
    "window.__ModuleLoader__.load({\n" +
    "  id: \"memory-recall-dsh\",\n" +
    "  factory: (require) => {\n" +
    "    var module = { exports: {} };\n" +
    "    var exports = module.exports;\n" +
    "    Object.defineProperty(exports, Symbol.toStringTag, { value: \"Module\" });\n" +
    "\n" +
    "    // ── 以下为 client-lib.js 源码（已剥离 export）──\n" +
    body + "\n" +
    "    // ── 插件形状：name / inject / apply（组合装载校验：函数或带 apply 的对象）──\n" +
    "    exports.name = \"memory-recall-dsh\";\n" +
    "    exports.inject = [];\n" +
    "    exports.apply = function apply(ctx) {\n" +
    "      ctx?.logger?.info?.('[memory-recall-dsh] browser client plugin loaded');\n" +
    "    };\n" +
    "\n" +
    "    // 顺带暴露 HTTP 客户端（bundle 内自包含，供浏览器侧调试/扩展使用）\n" +
    "    exports.MemoryRecallClient = MemoryRecallClient;\n" +
    "    exports.buildInjectConfig = buildInjectConfig;\n" +
    "    exports.ConfigurationError = ConfigurationError;\n" +
    "    return module.exports;\n" +
    "  }\n" +
    "});\n";
}

/** CLI 入口 */
if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const src = path.resolve(HERE, process.argv[2] ?? "client-lib.js");
  const dst = path.resolve(HERE, process.argv[3] ?? "client.js");
  const lib = fs.readFileSync(src, "utf8");
  fs.writeFileSync(dst, buildClientBundle(lib));
  console.log("已生成 %s（%d 字节）", dst, fs.statSync(dst).size);
}
