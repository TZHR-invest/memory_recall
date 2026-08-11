#!/usr/bin/env node

import { mkdirSync, writeFileSync, readFileSync, existsSync, rmSync, cpSync, symlinkSync, lstatSync, readlinkSync } from "node:fs";
import { join, dirname, resolve } from "node:path";
import { homedir } from "node:os";
import * as readline from "node:readline";
import { fileURLToPath, pathToFileURL } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const PLUGIN_NAME = "memory-recall-opencode";
const PLUGIN_REF = "./plugins/memory-recall-opencode";

const CONFIG_DIR = join(homedir(), ".config", "opencode");
const CACHE_DIR = join(homedir(), ".cache", "opencode");
const PLUGINS_DIR = join(CONFIG_DIR, "plugins");
const PLUGIN_INSTALL_DIR = join(PLUGINS_DIR, PLUGIN_NAME);

const OPENCODE_JSON = join(CONFIG_DIR, "opencode.json");
const PLUGIN_CONFIG_FILE = join(CONFIG_DIR, "memory-recall.jsonc");
const COMMAND_DIR = join(CONFIG_DIR, "command");
const CONFIG_PACKAGE_JSON = join(CONFIG_DIR, "package.json");

const CONFIG_NODE_MODULES = join(CONFIG_DIR, "node_modules");
const CACHE_NODE_MODULES = join(CACHE_DIR, "node_modules");
const CACHE_PACKAGES_DIR = join(CACHE_DIR, "packages");
const CACHE_PACKAGE_DIR = join(CACHE_PACKAGES_DIR, `${PLUGIN_NAME}@latest`);
const CONFIG_PLUGIN_SYMLINK = join(CONFIG_NODE_MODULES, PLUGIN_NAME);
const CACHE_PLUGIN_SYMLINK = join(CACHE_NODE_MODULES, PLUGIN_NAME);

let DEV_MODE = false;
let FORCE_MODE = false;

function createReadline(): readline.Interface {
  return readline.createInterface({
    input: process.stdin,
    output: process.stdout,
  });
}

async function question(rl: readline.Interface, prompt: string): Promise<string> {
  return new Promise((resolve) => {
    rl.question(prompt, (answer) => {
      resolve(answer.trim());
    });
  });
}

async function questionWithDefault(rl: readline.Interface, prompt: string, defaultValue: string): Promise<string> {
  return new Promise((resolve) => {
    rl.question(`${prompt} [${defaultValue}]: `, (answer) => {
      resolve(answer.trim() || defaultValue);
    });
  });
}

async function confirm(rl: readline.Interface, prompt: string): Promise<boolean> {
  return new Promise((resolve) => {
    rl.question(`${prompt} (y/n): `, (answer) => {
      resolve(answer.toLowerCase() === "y" || answer.toLowerCase() === "yes");
    });
  });
}

async function selectOption(rl: readline.Interface, prompt: string, options: string[]): Promise<number> {
  console.log(`\n${prompt}`);
  options.forEach((opt, idx) => {
    console.log(`  ${idx + 1}. ${opt}`);
  });
  
  while (true) {
    const answer = await question(rl, "请选择 (输入数字): ");
    const num = parseInt(answer);
    if (num >= 1 && num <= options.length) {
      return num - 1;
    }
    console.log("无效选择，请重新输入。");
  }
}

function stripJsoncComments(content: string): string {
  const protectedStrings: string[] = [];
  const STRING_PLACEHOLDER_PREFIX = "__JSONC_STR_";
  
  const withoutStrings = content.replace(/"(?:[^"\\]|\\.)*"/g, (match) => {
    protectedStrings.push(match);
    return `${STRING_PLACEHOLDER_PREFIX}${protectedStrings.length - 1}__`;
  });

  const withoutComments = withoutStrings
    .replace(/\/\/.*$/gm, "")
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/,(\s*[}\]])/g, "$1");

  return withoutComments.replace(
    new RegExp(`${STRING_PLACEHOLDER_PREFIX}(\\d+)__`, "g"),
    (_, idx) => protectedStrings[parseInt(idx)]
  );
}

function findOpencodeConfig(): string | null {
  const candidates = [
    join(CONFIG_DIR, "opencode.jsonc"),
    join(CONFIG_DIR, "opencode.json"),
  ];
  for (const path of candidates) {
    if (existsSync(path)) return path;
  }
  return null;
}

function getPluginSourcePath(): string {
  return dirname(__dirname);
}

function getPluginFileUrl(): string {
  const sourcePath = getPluginSourcePath();
  const absolutePath = resolve(sourcePath);
  return pathToFileURL(absolutePath).href;
}

function installPluginFiles(): { success: boolean; error?: string } {
  if (!existsSync(PLUGINS_DIR)) {
    try {
      mkdirSync(PLUGINS_DIR, { recursive: true });
      console.log(`✓ 创建插件目录: ${PLUGINS_DIR}`);
    } catch (error) {
      return { success: false, error: `创建插件目录失败: ${error}` };
    }
  }

  const sourcePath = getPluginSourcePath();
  const distPath = join(sourcePath, "dist");
  
  if (!existsSync(distPath)) {
    return { success: false, error: `插件未构建，dist 目录不存在` };
  }

  if (existsSync(PLUGIN_INSTALL_DIR)) {
    try {
      rmSync(PLUGIN_INSTALL_DIR, { recursive: true, force: true });
      console.log(`✓ 已删除旧插件: ${PLUGIN_INSTALL_DIR}`);
    } catch (error) {
      return { success: false, error: `删除旧插件失败: ${error}` };
    }
  }

  try {
    mkdirSync(PLUGIN_INSTALL_DIR, { recursive: true });
    
    cpSync(distPath, join(PLUGIN_INSTALL_DIR, "dist"), { recursive: true });
    cpSync(join(sourcePath, "package.json"), join(PLUGIN_INSTALL_DIR, "package.json"));
    
    const readmePath = join(sourcePath, "README.md");
    if (existsSync(readmePath)) {
      cpSync(readmePath, join(PLUGIN_INSTALL_DIR, "README.md"));
    }
    
    console.log(`✓ 插件已安装到: ${PLUGIN_INSTALL_DIR}`);
    return { success: true };
  } catch (error) {
    return { success: false, error: `复制插件文件失败: ${error}` };
  }
}

function createDevModeSymlink(): { success: boolean; error?: string } {
  const sourcePath = getPluginSourcePath();
  
  // 1. 创建 ~/.config/opencode/node_modules/memory-recall-opencode 符号链接
  if (!existsSync(CONFIG_NODE_MODULES)) {
    try {
      mkdirSync(CONFIG_NODE_MODULES, { recursive: true });
      console.log(`✓ 创建 node_modules 目录: ${CONFIG_NODE_MODULES}`);
    } catch (error) {
      return { success: false, error: `创建 node_modules 目录失败: ${error}` };
    }
  }
  
  if (existsSync(CONFIG_PLUGIN_SYMLINK)) {
    try {
      const stats = lstatSync(CONFIG_PLUGIN_SYMLINK);
      if (stats.isSymbolicLink()) {
        const existingTarget = readlinkSync(CONFIG_PLUGIN_SYMLINK);
        if (existingTarget === sourcePath || existingTarget === resolve(sourcePath)) {
          console.log(`✓ 符号链接已存在且正确: ${CONFIG_PLUGIN_SYMLINK}`);
          console.log(`  指向: ${sourcePath}`);
        } else {
          rmSync(CONFIG_PLUGIN_SYMLINK, { recursive: true, force: true });
          console.log(`✓ 已删除旧的符号链接`);
          symlinkSync(sourcePath, CONFIG_PLUGIN_SYMLINK, "junction");
          console.log(`✓ 已创建符号链接: ${CONFIG_PLUGIN_SYMLINK}`);
          console.log(`  指向: ${sourcePath}`);
        }
      } else {
        rmSync(CONFIG_PLUGIN_SYMLINK, { recursive: true, force: true });
        symlinkSync(sourcePath, CONFIG_PLUGIN_SYMLINK, "junction");
        console.log(`✓ 已创建符号链接: ${CONFIG_PLUGIN_SYMLINK}`);
        console.log(`  指向: ${sourcePath}`);
      }
    } catch (error) {
      return { success: false, error: `检查符号链接失败: ${error}` };
    }
  } else {
    try {
      symlinkSync(sourcePath, CONFIG_PLUGIN_SYMLINK, "junction");
      console.log(`✓ 已创建符号链接: ${CONFIG_PLUGIN_SYMLINK}`);
      console.log(`  指向: ${sourcePath}`);
    } catch {
      try {
        symlinkSync(sourcePath, CONFIG_PLUGIN_SYMLINK, "dir");
        console.log(`✓ 已创建符号链接: ${CONFIG_PLUGIN_SYMLINK}`);
        console.log(`  指向: ${sourcePath}`);
      } catch (error2) {
        return { success: false, error: `创建符号链接失败: ${error2}` };
      }
    }
  }
  
  // 2. 创建 ~/.cache/opencode/packages/memory-recall-opencode@latest/ 入口
  const cacheNodeModules = join(CACHE_PACKAGE_DIR, "node_modules");
  const cachePluginLink = join(cacheNodeModules, PLUGIN_NAME);
  const cacheDepsLink = join(cacheNodeModules, "@opencode-ai");
  
  try {
    mkdirSync(cacheNodeModules, { recursive: true });
    
    const packageJsonPath = join(CACHE_PACKAGE_DIR, "package.json");
    writeFileSync(packageJsonPath, JSON.stringify({
      name: PLUGIN_NAME,
      version: "1.8.1"
    }, null, 2));
    console.log(`✓ 创建 packages 入口: ${CACHE_PACKAGE_DIR}`);
    
    // 创建插件符号链接
    if (existsSync(cachePluginLink)) {
      rmSync(cachePluginLink, { recursive: true, force: true });
    }
    symlinkSync(sourcePath, cachePluginLink, "junction");
    console.log(`  插件链接: ${cachePluginLink}`);
    
    // 创建依赖符号链接
    if (existsSync(CONFIG_NODE_MODULES) && existsSync(join(CONFIG_NODE_MODULES, "@opencode-ai"))) {
      if (existsSync(cacheDepsLink)) {
        rmSync(cacheDepsLink, { recursive: true, force: true });
      }
      symlinkSync(join(CONFIG_NODE_MODULES, "@opencode-ai"), cacheDepsLink, "junction");
      console.log(`  依赖链接: ${cacheDepsLink}`);
    }
    
    // zod 依赖
    const zodLink = join(cacheNodeModules, "zod");
    if (existsSync(CONFIG_NODE_MODULES) && existsSync(join(CONFIG_NODE_MODULES, "zod"))) {
      if (existsSync(zodLink)) {
        rmSync(zodLink, { recursive: true, force: true });
      }
      symlinkSync(join(CONFIG_NODE_MODULES, "zod"), zodLink, "junction");
    }
    
  } catch (error) {
    return { success: false, error: `创建 packages 入口失败: ${error}` };
  }
  
  return { success: true };
}

function uninstallPluginFiles(): boolean {
  let success = true;
  
  // 1. 清理 ~/.config/opencode/plugins/memory-recall-opencode/
  if (existsSync(PLUGIN_INSTALL_DIR)) {
    try {
      rmSync(PLUGIN_INSTALL_DIR, { recursive: true, force: true });
      console.log(`✓ 已删除插件文件: ${PLUGIN_INSTALL_DIR}`);
    } catch (error) {
      console.log(`✗ 删除插件文件失败: ${error}`);
      success = false;
    }
  }
  
  // 2. 清理 ~/.config/opencode/node_modules/memory-recall-opencode/ (可能是符号链接或目录)
  if (existsSync(CONFIG_PLUGIN_SYMLINK)) {
    try {
      rmSync(CONFIG_PLUGIN_SYMLINK, { recursive: true, force: true });
      console.log(`✓ 已删除 config/node_modules 中的插件: ${CONFIG_PLUGIN_SYMLINK}`);
    } catch (error) {
      console.log(`✗ 删除 config/node_modules 插件失败: ${error}`);
      success = false;
    }
  }
  
  // 3. 清理 ~/.cache/opencode/node_modules/memory-recall-opencode/ (OpenCode 安装的缓存)
  if (existsSync(CACHE_PLUGIN_SYMLINK)) {
    try {
      rmSync(CACHE_PLUGIN_SYMLINK, { recursive: true, force: true });
      console.log(`✓ 已删除 cache/node_modules 中的插件: ${CACHE_PLUGIN_SYMLINK}`);
    } catch (error) {
      console.log(`✗ 删除 cache/node_modules 插件失败: ${error}`);
      success = false;
    }
  }
  
  if (existsSync(CACHE_PACKAGE_DIR)) {
    try {
      rmSync(CACHE_PACKAGE_DIR, { recursive: true, force: true });
      console.log(`✓ 已删除 cache/packages 中的插件: ${CACHE_PACKAGE_DIR}`);
    } catch (error) {
      console.log(`✗ 删除 cache/packages 插件失败: ${error}`);
      success = false;
    }
  }
  
  return success;
}

function registerPluginToOpencode(): void {
  mkdirSync(CONFIG_DIR, { recursive: true });
  
  const configPath = findOpencodeConfig();
  const pluginRef = DEV_MODE ? getPluginFileUrl() : PLUGIN_REF;
  
  if (!configPath) {
    const newConfig = `{
  "plugin": ["${pluginRef}"]
}
`;
    writeFileSync(join(CONFIG_DIR, "opencode.jsonc"), newConfig);
    console.log(`✓ 已创建 opencode.jsonc 并注册插件`);
    if (DEV_MODE) {
      console.log(`  开发模式: ${pluginRef}`);
    }
    return;
  }

  const content = readFileSync(configPath, "utf-8");
  
  const hasPluginRef = 
    content.includes(PLUGIN_REF) || 
    content.includes(PLUGIN_NAME) || 
    content.includes(getPluginFileUrl());
  
  if (hasPluginRef) {
    console.log(`✓ 插件已在 opencode.json 中注册`);
    return;
  }

  if (configPath.endsWith(".jsonc")) {
    if (content.includes('"plugin"')) {
      const newContent = content.replace(
        /("plugin"\s*:\s*\[)([^\]]*?)(\])/,
        (_match, start, middle, end) => {
          const trimmed = middle.trim();
          if (trimmed === "") {
            return `${start}\n    "${pluginRef}"\n  ${end}`;
          }
          return `${start}${middle.trimEnd()},\n    "${pluginRef}"\n  ${end}`;
        }
      );
      writeFileSync(configPath, newContent);
    } else {
      const newContent = content.replace(
        /^(\s*\{)/,
        `$1\n  "plugin": ["${pluginRef}"],`
      );
      writeFileSync(configPath, newContent);
    }
  } else {
    const jsonContent = stripJsoncComments(content);
    const config = JSON.parse(jsonContent);
    const plugins = (config.plugin as string[]) || [];
    plugins.push(pluginRef);
    config.plugin = plugins;
    writeFileSync(configPath, JSON.stringify(config, null, 2));
  }

  console.log(`✓ 已注册插件到 opencode.json`);
  if (DEV_MODE) {
    console.log(`  开发模式: ${pluginRef}`);
  } else {
    console.log(`  引用路径: ${PLUGIN_REF}`);
  }
}

function unregisterPluginFromOpencode(): void {
  const configPath = findOpencodeConfig();
  if (!configPath) return;

  const content = readFileSync(configPath, "utf-8");
  const pluginFileUrl = getPluginFileUrl();
  
  const hasPluginRef = 
    content.includes(PLUGIN_REF) || 
    content.includes(PLUGIN_NAME) || 
    content.includes(pluginFileUrl);
    
  if (!hasPluginRef) return;

  function escapeRegex(str: string): string {
    return str.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  }

  if (configPath.endsWith(".jsonc")) {
    let newContent = content
      .replace(new RegExp(`,?\\s*"${escapeRegex(PLUGIN_REF)}"\\s*,?`, "g"), "")
      .replace(new RegExp(`,?\\s*"${escapeRegex(PLUGIN_NAME)}"\\s*,?`, "g"), "")
      .replace(new RegExp(`,?\\s*"${escapeRegex(pluginFileUrl)}"\\s*,?`, "g"), "")
      .replace(/\[\s*,/g, "[")
      .replace(/,\s*\]/g, "]");
    writeFileSync(configPath, newContent);
  } else {
    const jsonContent = stripJsoncComments(content);
    const config = JSON.parse(jsonContent);
    if (config.plugin && Array.isArray(config.plugin)) {
      config.plugin = config.plugin.filter(
        (p: string) => p !== PLUGIN_REF && p !== PLUGIN_NAME && p !== pluginFileUrl
      );
      writeFileSync(configPath, JSON.stringify(config, null, 2));
    }
  }

  console.log(`✓ 已从 opencode.json 移除插件`);
}

function registerPluginToPackageJson(): void {
  const sourcePath = getPluginSourcePath();
  const pluginPackageJsonPath = join(sourcePath, "package.json");
  
  let pluginDeps: Record<string, string> = {};
  
  if (existsSync(pluginPackageJsonPath)) {
    try {
      const pluginPackageJson = JSON.parse(readFileSync(pluginPackageJsonPath, "utf-8"));
      pluginDeps = pluginPackageJson.dependencies || {};
    } catch {}
  }

  if (!existsSync(CONFIG_PACKAGE_JSON)) {
    const packageJson = {
      name: "opencode-plugins",
      private: true,
      dependencies: pluginDeps
    };
    writeFileSync(CONFIG_PACKAGE_JSON, JSON.stringify(packageJson, null, 2));
    console.log(`✓ 已创建 package.json`);
    if (Object.keys(pluginDeps).length > 0) {
      console.log(`  运行时依赖: ${Object.keys(pluginDeps).join(", ")}`);
    }
    console.log(`  OpenCode 启动时将自动安装依赖 (bun install)`);
    return;
  }

  const content = readFileSync(CONFIG_PACKAGE_JSON, "utf-8");
  const packageJson = JSON.parse(content);
  
  if (!packageJson.dependencies) {
    packageJson.dependencies = {};
  }
  
  let addedCount = 0;
  for (const [name, version] of Object.entries(pluginDeps)) {
    if (!packageJson.dependencies[name] && name !== PLUGIN_NAME) {
      packageJson.dependencies[name] = version;
      addedCount++;
    }
  }
  
  writeFileSync(CONFIG_PACKAGE_JSON, JSON.stringify(packageJson, null, 2));
  
  if (addedCount > 0) {
    console.log(`✓ 已更新 package.json，新增 ${addedCount} 个依赖`);
    console.log(`  OpenCode 启动时将自动安装依赖 (bun install)`);
  } else {
    console.log(`✓ package.json 已是最新`);
  }
}

function unregisterPluginFromPackageJson(removeDependencies: boolean = false): void {
  if (!existsSync(CONFIG_PACKAGE_JSON)) return;

  const content = readFileSync(CONFIG_PACKAGE_JSON, "utf-8");
  const packageJson = JSON.parse(content);
  let modified = false;
  
  // 移除插件本身
  if (packageJson.dependencies && packageJson.dependencies[PLUGIN_NAME]) {
    delete packageJson.dependencies[PLUGIN_NAME];
    modified = true;
    console.log(`✓ 已从 package.json 移除插件`);
  }
  
  // 可选：移除插件依赖（@opencode-ai/plugin, @opencode-ai/sdk, zod）
  if (removeDependencies) {
    const pluginDeps = ["@opencode-ai/plugin", "@opencode-ai/sdk", "zod"];
    for (const dep of pluginDeps) {
      if (packageJson.dependencies && packageJson.dependencies[dep]) {
        delete packageJson.dependencies[dep];
        modified = true;
      }
    }
    if (modified) {
      console.log(`✓ 已从 package.json 移除插件依赖`);
    }
  }
  
  if (modified) {
    writeFileSync(CONFIG_PACKAGE_JSON, JSON.stringify(packageJson, null, 2));
  }
}

function createCommands(): void {
  mkdirSync(COMMAND_DIR, { recursive: true });
  
  const initCommand = `---
description: 初始化 Memory Recall，导入代码库知识
---

[search-mode]
最大化搜索效率。并行启动多个后台代理：
- explore 代理（代码库模式、文件结构、ast-grep）
- librarian 代理（远程仓库、官方文档、GitHub 示例）
同时使用直接工具：Grep、ripgrep (rg)、ast-grep (sg)
不要在第一个结果就停止 - 要彻底搜索。

---

# 初始化 Memory Recall

## 第一步：导入项目文档

首先导入现有文档：

\`\`\`
memory-recall(mode: "import-docs")
\`\`\`

这将导入 README.md、CHANGELOG.md、docs/*.md、AGENTS.md 等文件。

## 第二步：探索代码库

并行使用多个 explore 查询：

\`\`\`
Task(explore, "技术栈和依赖是什么？")
Task(explore, "项目结构是怎样的？")
Task(explore, "如何构建、测试和运行？")
\`\`\`

## 第三步：保存知识

使用 \`memory-recall\` 工具保存每个发现：

\`\`\`
memory-recall(mode: "add", content: "...", type: "project-config", scope: "project")
\`\`\`

**知识类型：** project-config（项目配置）、architecture（架构）、learned-pattern（学习到的模式）、preference（偏好）、error-solution（错误解决方案）
**作用域：** project（本项目）、user（跨项目）

## 第四步：确认

告诉用户导入了什么、保存了什么。

[MEMORY TRIGGER DETECTED]
如果用户希望您记住某些内容，请使用 \`memory-recall\` 工具的 \`mode: "add"\` 来保存。

- 使用 \`scope: "project"\` 保存项目相关偏好
- 使用 \`scope: "user"\` 保存跨项目偏好

请勿跳过此步骤。
`;

  writeFileSync(join(COMMAND_DIR, "memory-init.md"), initCommand);
  console.log(`✓ 已创建 /memory-init 命令`);
}

function removeCommands(): void {
  const initPath = join(COMMAND_DIR, "memory-init.md");
  if (existsSync(initPath)) {
    rmSync(initPath);
    console.log(`✓ 已删除 /memory-init 命令`);
  }
}

function configExists(): boolean {
  return existsSync(PLUGIN_CONFIG_FILE);
}

function readConfig(): Record<string, unknown> | null {
  if (!existsSync(PLUGIN_CONFIG_FILE)) return null;
  try {
    const content = readFileSync(PLUGIN_CONFIG_FILE, "utf-8");
    return JSON.parse(stripJsoncComments(content));
  } catch {
    return null;
  }
}

function deleteConfig(): void {
  if (existsSync(PLUGIN_CONFIG_FILE)) {
    rmSync(PLUGIN_CONFIG_FILE);
    console.log(`✓ 已删除配置文件: ${PLUGIN_CONFIG_FILE}`);
  }
}

function writeConfig(config: {
  apiKey: string;
  baseUrl: string;
  userName: string;
  keyId: string;
}, preserveExisting: boolean = false): void {
  // 如果保留现有配置，尝试合并
  if (preserveExisting && existsSync(PLUGIN_CONFIG_FILE)) {
    try {
      const existing = readConfig();
      if (existing) {
        // 合并配置：只更新基本配置，保留用户自定义配置
        const merged = {
          ...existing,  // 保留所有现有配置
          apiKey: config.apiKey,  // 更新基本配置
          baseUrl: config.baseUrl,
          userName: config.userName,
          keyId: config.keyId,
        };
        
        const mergedContent = JSON.stringify(merged, null, 2);
        writeFileSync(PLUGIN_CONFIG_FILE, mergedContent);
        console.log(`✓ 配置已更新并保留自定义设置`);
        return;
      }
    } catch (e) {
      console.log("⚠️  无法读取现有配置，将创建新配置");
    }
  }
  
  // 创建新配置（默认值）
  const content = `{
  "apiKey": "${config.apiKey}",
  "baseUrl": "${config.baseUrl}",
  "userName": "${config.userName}",
  "keyId": "${config.keyId}",

  // 检索配置
  "similarityThreshold": 0.4,
  "maxMemories": 5,
  "maxProjectMemories": 10,
  "injectProfile": true,
  "compactionThreshold": 0.8,
  "enableSummaryCapture": true,
  "enableDocumentTracking": true,
  "trackedDocPatterns": ["README*.md", "CHANGELOG*.md", "docs/*.md", "AGENTS.md"],

  // Chunks 配置
  "enableChunksSearch": true,
  "maxChunks": 5,
  "chunksSimilarityThreshold": 0.45,

  // Graph 和 Entity 召回
  "enableGraphRecall": true,
  "enableEntityRecall": true,
  "graphMaxDepth": 2,
  "graphMaxNodes": 5,

  // 注入策略
  "injectionStrategy": "smart",
  "initialInjection": {
    "profile": true,
    "projectMemories": true,
    "chunks": true,
    "maxChunks": 3
  },
  "smartRecall": {
    "enabled": true,
    "keywords": ["记得", "之前", "上次", "以前", "回忆", "记忆", "recall", "remember", "previous", "earlier"],
    "maxAdditionalMemories": 3,
    "maxAdditionalChunks": 2
  },

  // 后端语义去重（v5.1 新增）
  "useBackendDedup": true,
  "semanticDedup": {
    "enabled": true,
    "threshold": 0.85,
    "maxBatchSize": 50
  },

  // 异步写入队列（v5.2 新增）
  "asyncQueue": {
    "enabled": true,
    "maxConcurrency": 3,
    "maxSize": 100,
    "taskTimeoutMs": 120000,
    "retryPolicy": {
      "maxRetries": 3,
      "initialDelay": 1000,
      "maxDelay": 10000,
      "backoffMultiplier": 2
    }
  },

  "language": "auto",
  "logLevel": "info"
}
`;
  mkdirSync(CONFIG_DIR, { recursive: true });
  writeFileSync(PLUGIN_CONFIG_FILE, content);
  console.log(`✓ 配置已保存到 ${PLUGIN_CONFIG_FILE}`);
}

async function validateApiKey(baseUrl: string, apiKey: string): Promise<{ valid: boolean; keyId?: string; userName?: string; error?: string }> {
  try {
    const response = await fetch(`${baseUrl}/auth/verify`, {
      method: "GET",
      headers: {
        "X-API-Key": apiKey,
        "Content-Type": "application/json",
      },
    });

    if (response.ok) {
      const data = await response.json() as { key_id: string; user_name?: string };
      return { 
        valid: true, 
        keyId: data.key_id,
        userName: data.user_name,
      };
    }
    if (response.status === 401) return { valid: false, error: "API Key 无效" };
    if (response.status === 403) return { valid: false, error: "API Key 无权限" };
    return { valid: false, error: `服务器错误: ${response.status}` };
  } catch (error) {
    return { valid: false, error: `无法连接服务器: ${error}` };
  }
}

async function registerNewUser(
  baseUrl: string,
  userName: string
): Promise<{ success: boolean; apiKey?: string; keyId?: string; error?: string }> {
  try {
    const response = await fetch(`${baseUrl}/auth/initialize`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        plugin_name: "opencode-plugin",
        user_name: userName,
        permissions: ["read", "write", "delete", "admin"],
      }),
    });

    if (response.ok) {
      const data = await response.json() as { api_key: string; key_id: string };
      return {
        success: true,
        apiKey: data.api_key,
        keyId: data.key_id,
      };
    } else if (response.status === 403) {
      return { success: false, error: "服务器已有 API Key，请选择'使用已有 API Key'" };
    } else {
      return { success: false, error: `注册失败: ${response.status}` };
    }
  } catch (error) {
    return { success: false, error: `无法连接服务器: ${error}` };
  }
}

async function doInstall(): Promise<void> {
  console.log("\n╔════════════════════════════════════════════╗");
  if (DEV_MODE) {
    console.log("║   Memory Recall OpenCode 插件安装向导     ║");
    console.log("║          【开发模式】                      ║");
  } else {
    console.log("║   Memory Recall OpenCode 插件安装向导     ║");
  }
  console.log("╚════════════════════════════════════════════╝\n");

  const rl = createReadline();

  try {
    console.log("【步骤 1/4】安装插件文件\n");
    
    if (DEV_MODE) {
      const sourcePath = getPluginSourcePath();
      const distPath = join(sourcePath, "dist");
      if (!existsSync(distPath)) {
        console.log(`✗ 插件未构建，dist 目录不存在`);
        console.log(`  请先运行: bun run build`);
        return;
      }
      console.log(`✓ 开发模式: 直接加载源码目录`);
      console.log(`  路径: ${sourcePath}`);
      
      const symlinkResult = createDevModeSymlink();
      if (!symlinkResult.success) {
        console.log(`✗ ${symlinkResult.error}`);
        return;
      }
    } else {
      const installResult = installPluginFiles();
      if (!installResult.success) {
        console.log(`✗ ${installResult.error}`);
        return;
      }
    }

    console.log("\n【步骤 2/4】注册插件和依赖\n");
    registerPluginToOpencode();
    // 开发模式也需要声明依赖，确保 OpenCode 启动时自动安装
    registerPluginToPackageJson();

    console.log("\n【步骤 3/4】创建命令\n");
    createCommands();

    console.log("\n【步骤 4/4】配置 API\n");
    
    if (configExists()) {
      const existingConfig = readConfig();
      if (existingConfig?.apiKey) {
        console.log("检测到已有配置:");
        console.log(`  API 地址: ${existingConfig.baseUrl || 'http://localhost:8000'}`);
        console.log(`  用户名: ${existingConfig.userName || 'User'}`);
        
        // v1.8.2 召回质量优化: 检测旧默认阈值(0.3)并提示迁移到推荐值(0.4/0.45)
        const legacyThreshold =
          (existingConfig.similarityThreshold as number) === 0.3 ||
          (existingConfig.chunksSimilarityThreshold as number) === 0.3;
        if (legacyThreshold) {
          const migrate = await confirm(
            rl,
            "\n检测到旧版默认阈值 (similarityThreshold=0.3 / chunksSimilarityThreshold=0.3)。\nv1.8.2 召回质量优化推荐 0.4 / 0.45 以过滤低相关记忆，是否更新阈值配置? (y/n)"
          );
          if (migrate) {
            const updated = {
              ...existingConfig,
              similarityThreshold: 0.4,
              chunksSimilarityThreshold: 0.45,
            };
            writeFileSync(PLUGIN_CONFIG_FILE, JSON.stringify(updated, null, 2));
            console.log("✓ 阈值已更新: similarityThreshold=0.4, chunksSimilarityThreshold=0.45");
          }
        }
        
        const reconfigure = await confirm(rl, "\n是否重新配置? (y/n)");
        if (!reconfigure) {
          console.log("\n╔════════════════════════════════════════════╗");
          console.log("║              安装完成！                    ║");
          console.log("╚════════════════════════════════════════════╝");
          console.log("\n下一步:");
          console.log("  1. 确保 Memory Recall API 服务正在运行");
          console.log("  2. 重启 OpenCode（依赖将自动安装）\n");
          return;
        }
      }
    }

    const userType = await selectOption(rl, "请选择配置方式:", [
      "使用已有 API Key",
      "注册新用户 (开发环境首次使用)",
    ]);

    const baseUrl = await questionWithDefault(rl, "\nAPI 服务地址", "http://localhost:8000");

    let apiKey: string;
    let userName: string;
    let keyId: string;

    if (userType === 1) {
      userName = await question(rl, "请输入用户名: ");
      if (!userName) {
        console.log("✗ 用户名不能为空");
        return;
      }

      console.log("\n正在注册...");
      const result = await registerNewUser(baseUrl, userName);

      if (!result.success) {
        console.log(`✗ ${result.error}`);
        return;
      }

      apiKey = result.apiKey!;
      keyId = result.keyId!;

      console.log("\n╔════════════════════════════════════════════╗");
      console.log("║              注册成功！                    ║");
      console.log("╚════════════════════════════════════════════╝");
      console.log(`\n  API Key: ${apiKey}`);
      console.log(`  Key ID: ${keyId}`);
      console.log("\n⚠️  请妥善保存 API Key，此密钥只会显示一次！\n");
    } else {
      apiKey = await question(rl, "请输入 API Key: ");
      if (!apiKey) {
        console.log("✗ API Key 不能为空");
        return;
      }

      console.log("\n正在验证 API Key...");
      const validation = await validateApiKey(baseUrl, apiKey);

      if (!validation.valid) {
        console.log(`✗ ${validation.error}`);
        return;
      }

      console.log("✓ API Key 验证成功");
      
      keyId = validation.keyId!;
      userName = validation.userName || await questionWithDefault(rl, "请输入用户名", "User");
    }

    // 保留用户的自定义配置（如 asyncQueue、semanticDedup 等）
    writeConfig({ apiKey, baseUrl, userName, keyId }, true);

    console.log("\n╔════════════════════════════════════════════╗");
    console.log("║              安装完成！                    ║");
    console.log("╚════════════════════════════════════════════╝");
    console.log("\n下一步:");
    console.log("  1. 确保 Memory Recall API 服务正在运行");
    console.log("  2. 重启 OpenCode（依赖将自动安装）");
    console.log("  3. 使用 /memory-init 初始化项目记忆\n");

  } finally {
    rl.close();
  }
}

async function doUninstall(): Promise<void> {
  console.log("\n╔════════════════════════════════════════════╗");
  console.log("║   Memory Recall OpenCode 插件卸载         ║");
  console.log("╚════════════════════════════════════════════╝\n");

  const hasPlugin = existsSync(PLUGIN_INSTALL_DIR) || 
                    existsSync(CONFIG_PLUGIN_SYMLINK) || 
                    existsSync(CACHE_PLUGIN_SYMLINK);
  
  if (!configExists() && !hasPlugin) {
    console.log("未检测到已安装的插件，无需卸载。\n");
    return;
  }

  const existingConfig = readConfig();
  if (existingConfig) {
    console.log("当前配置:");
    console.log(`  API 地址: ${existingConfig.baseUrl || '未设置'}`);
    console.log(`  用户名: ${existingConfig.userName || '未设置'}`);
  }

  let confirmUninstall = FORCE_MODE;
  let removeDeps = false;

  if (!FORCE_MODE) {
    const rl = createReadline();
    try {
      confirmUninstall = await confirm(rl, "\n确定要卸载插件吗? (y/n)");
      if (!confirmUninstall) {
        console.log("\n卸载已取消。");
        return;
      }
      removeDeps = await confirm(rl, "是否同时移除插件依赖? (@opencode-ai/plugin, zod 等) (y/n)");
    } finally {
      rl.close();
    }
  }

  console.log("\n正在卸载...\n");
  
  deleteConfig();
  removeCommands();
  unregisterPluginFromOpencode();
  unregisterPluginFromPackageJson(removeDeps);
  uninstallPluginFiles();

  console.log("\n╔════════════════════════════════════════════╗");
  console.log("║              卸载完成！                    ║");
  console.log("╚════════════════════════════════════════════╝");
  console.log("\n如需重新安装，请运行:");
  console.log("  node dist/cli.js install\n");
}

async function doReinstall(): Promise<void> {
  console.log("\n╔════════════════════════════════════════════╗");
  console.log("║   Memory Recall OpenCode 插件重新安装     ║");
  console.log("╚════════════════════════════════════════════╝\n");

  const existingConfig = readConfig();
  if (existingConfig) {
    console.log("当前配置:");
    console.log(`  API 地址: ${existingConfig.baseUrl || '未设置'}`);
    console.log(`  用户名: ${existingConfig.userName || '未设置'}`);
  }

  const rl = createReadline();

  try {
    const confirmReinstall = await confirm(rl, "\n确定要重新安装吗? (将删除配置和插件文件) (y/n)");
    if (!confirmReinstall) {
      console.log("\n已取消。");
      return;
    }
  } finally {
    rl.close();
  }
  
  console.log("\n正在删除旧安装...\n");
  
  deleteConfig();
  removeCommands();
  unregisterPluginFromOpencode();
  unregisterPluginFromPackageJson(false);
  uninstallPluginFiles();

  console.log("");
  await doInstall();
}

function printHelp(): void {
  console.log(`
Memory Recall OpenCode 插件

用法:
  node dist/cli.js install          安装插件（生产模式）
  node dist/cli.js install --dev    安装插件（开发模式，直接加载源码）
  node dist/cli.js uninstall        卸载插件（交互式）
  node dist/cli.js uninstall --force 卸载插件（无需确认）
  node dist/cli.js reinstall        重新安装
  node dist/cli.js status           查看状态
  node dist/cli.js --help           显示帮助

安装位置:
  ~/.config/opencode/plugins/memory-recall-opencode/

配置文件:
  ~/.config/opencode/memory-recall.jsonc
`);
}

async function showStatus(): Promise<void> {
  console.log("\n=== Memory Recall 插件状态 ===\n");

  const sourcePath = getPluginSourcePath();

  const hasInstalled = existsSync(PLUGIN_INSTALL_DIR);
  const hasConfigSymlink = existsSync(CONFIG_PLUGIN_SYMLINK);
  const hasCacheSymlink = existsSync(CACHE_PLUGIN_SYMLINK);
  
  if (hasInstalled) {
    console.log(`✓ 插件文件: ${PLUGIN_INSTALL_DIR}`);
  } else {
    console.log("✗ 插件文件未安装");
  }
  
  if (hasConfigSymlink) {
    try {
      const stats = lstatSync(CONFIG_PLUGIN_SYMLINK);
      if (stats.isSymbolicLink()) {
        const target = readlinkSync(CONFIG_PLUGIN_SYMLINK);
        console.log(`✓ config/node_modules (符号链接): ${CONFIG_PLUGIN_SYMLINK}`);
        console.log(`  → 指向: ${target}`);
        if (target === sourcePath || target === resolve(sourcePath)) {
          console.log(`  [开发模式]`);
        }
      } else {
        console.log(`✓ config/node_modules (目录): ${CONFIG_PLUGIN_SYMLINK}`);
      }
    } catch {
      console.log(`✓ config/node_modules: ${CONFIG_PLUGIN_SYMLINK}`);
    }
  }
  
  if (hasCacheSymlink) {
    console.log(`✓ cache/node_modules: ${CACHE_PLUGIN_SYMLINK}`);
  }
  
  if (existsSync(CACHE_PACKAGE_DIR)) {
    const cachePluginLink = join(CACHE_PACKAGE_DIR, "node_modules", PLUGIN_NAME);
    if (existsSync(cachePluginLink)) {
      try {
        const stats = lstatSync(cachePluginLink);
        if (stats.isSymbolicLink()) {
          const target = readlinkSync(cachePluginLink);
          console.log(`✓ cache/packages (符号链接): ${cachePluginLink}`);
          console.log(`  → 指向: ${target}`);
        } else {
          console.log(`✓ cache/packages: ${cachePluginLink}`);
        }
      } catch {
        console.log(`✓ cache/packages: ${CACHE_PACKAGE_DIR}`);
      }
    }
  }

  if (existsSync(join(sourcePath, "dist"))) {
    console.log(`\n✓ 源码可构建: ${sourcePath}`);
  } else {
    console.log(`\n✗ 源码未构建: ${sourcePath}/dist 不存在`);
  }

  // 检查 opencode.json 注册
  const configPath = findOpencodeConfig();
  if (configPath) {
    const content = readFileSync(configPath, "utf-8");
    const hasRef = 
      content.includes(PLUGIN_REF) || 
      content.includes(PLUGIN_NAME) || 
      content.includes(getPluginFileUrl());
    
    if (hasRef) {
      if (content.includes(getPluginFileUrl())) {
        console.log(`\n✓ 插件已注册 (开发模式: file:// URL)`);
      } else if (content.includes(PLUGIN_REF)) {
        console.log(`\n✓ 插件已注册 (生产模式: 相对路径)`);
      } else {
        console.log(`\n✓ 插件已注册`);
      }
    } else {
      console.log(`\n✗ 插件未在 opencode.json 中注册`);
    }
  }

  // 检查依赖配置
  if (existsSync(CONFIG_PACKAGE_JSON)) {
    const content = readFileSync(CONFIG_PACKAGE_JSON, "utf-8");
    const packageJson = JSON.parse(content);
    const deps = Object.keys(packageJson.dependencies || {});
    const pluginDeps = ["@opencode-ai/plugin", "@opencode-ai/sdk", "zod"];
    const hasPluginDeps = pluginDeps.some(d => packageJson.dependencies?.[d]);
    if (hasPluginDeps) {
      console.log(`\n✓ 依赖已配置: ${pluginDeps.filter(d => packageJson.dependencies?.[d]).join(", ")}`);
    }
  }

  // 检查 API 配置
  const config = readConfig();
  if (config?.apiKey) {
    console.log(`\n✓ API 已配置`);
    console.log(`  地址: ${config.baseUrl || '未设置'}`);
    console.log(`  用户: ${config.userName || '未设置'}`);
  } else {
    console.log(`\n✗ API 未配置`);
  }

  // 检查命令
  const initPath = join(COMMAND_DIR, "memory-init.md");
  if (existsSync(initPath)) {
    console.log(`\n✓ /memory-init 命令可用`);
  }

  console.log("");
}

async function main(): Promise<void> {
  const args = process.argv.slice(2);
  const command = args[0] || "install";
  
  DEV_MODE = args.includes("--dev") || args.includes("-d");
  FORCE_MODE = args.includes("--force") || args.includes("-f");

  switch (command) {
    case "install":
    case "i":
      await doInstall();
      break;
    case "uninstall":
    case "u":
      await doUninstall();
      break;
    case "reinstall":
    case "r":
      await doReinstall();
      break;
    case "status":
    case "s":
      await showStatus();
      break;
    case "--help":
    case "-h":
    case "help":
      printHelp();
      break;
    default:
      if (command.startsWith("--")) {
        await doInstall();
      } else {
        console.log(`未知命令: ${command}`);
        printHelp();
        process.exit(1);
      }
  }
}

main().catch((error) => {
  console.error("执行出错:", error);
  process.exit(1);
});
