#!/usr/bin/env node

import { mkdirSync, writeFileSync, readFileSync, existsSync, rmSync, cpSync } from "node:fs";
import { join, dirname } from "node:path";
import { homedir } from "node:os";
import * as readline from "node:readline";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const OPENCODE_CONFIG_DIR = join(homedir(), ".config", "opencode");
const OPENCODE_COMMAND_DIR = join(OPENCODE_CONFIG_DIR, "command");
const NODE_MODULES_DIR = join(OPENCODE_CONFIG_DIR, "node_modules");
const PLUGIN_INSTALL_DIR = join(NODE_MODULES_DIR, "memory-recall-opencode");
const CONFIG_FILE = join(OPENCODE_CONFIG_DIR, "memory-recall.jsonc");
const PACKAGE_JSON_FILE = join(OPENCODE_CONFIG_DIR, "package.json");
const PLUGIN_NAME = "memory-recall-opencode";

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
    join(OPENCODE_CONFIG_DIR, "opencode.jsonc"),
    join(OPENCODE_CONFIG_DIR, "opencode.json"),
  ];
  for (const path of candidates) {
    if (existsSync(path)) return path;
  }
  return null;
}

function getPluginSourcePath(): string {
  return dirname(__dirname);
}

function installPluginFiles(): { success: boolean; error?: string } {
  if (!existsSync(NODE_MODULES_DIR)) {
    try {
      mkdirSync(NODE_MODULES_DIR, { recursive: true });
      console.log(`✓ 创建插件目录: ${NODE_MODULES_DIR}`);
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
    cpSync(sourcePath, PLUGIN_INSTALL_DIR, { recursive: true });
    console.log(`✓ 插件已安装到: ${PLUGIN_INSTALL_DIR}`);
    return { success: true };
  } catch (error) {
    return { success: false, error: `复制插件文件失败: ${error}` };
  }
}

function uninstallPluginFiles(): boolean {
  if (existsSync(PLUGIN_INSTALL_DIR)) {
    try {
      rmSync(PLUGIN_INSTALL_DIR, { recursive: true, force: true });
      console.log(`✓ 已删除插件文件: ${PLUGIN_INSTALL_DIR}`);
      return true;
    } catch (error) {
      console.log(`✗ 删除插件文件失败: ${error}`);
      return false;
    }
  }
  return true;
}

function registerPluginToOpencode(): void {
  mkdirSync(OPENCODE_CONFIG_DIR, { recursive: true });
  
  const configPath = findOpencodeConfig();
  
  if (!configPath) {
    const newConfig = `{
  "plugin": ["${PLUGIN_NAME}"]
}
`;
    writeFileSync(join(OPENCODE_CONFIG_DIR, "opencode.jsonc"), newConfig);
    console.log(`✓ 已创建 opencode.jsonc 并注册插件`);
    return;
  }

  const content = readFileSync(configPath, "utf-8");
  
  if (content.includes(PLUGIN_NAME)) {
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
            return `${start}\n    "${PLUGIN_NAME}"\n  ${end}`;
          }
          return `${start}${middle.trimEnd()},\n    "${PLUGIN_NAME}"\n  ${end}`;
        }
      );
      writeFileSync(configPath, newContent);
    } else {
      const newContent = content.replace(
        /^(\s*\{)/,
        `$1\n  "plugin": ["${PLUGIN_NAME}"],`
      );
      writeFileSync(configPath, newContent);
    }
  } else {
    const jsonContent = stripJsoncComments(content);
    const config = JSON.parse(jsonContent);
    const plugins = (config.plugin as string[]) || [];
    plugins.push(PLUGIN_NAME);
    config.plugin = plugins;
    writeFileSync(configPath, JSON.stringify(config, null, 2));
  }

  console.log(`✓ 已注册插件到 opencode.json`);
}

function unregisterPluginFromOpencode(): void {
  const configPath = findOpencodeConfig();
  if (!configPath) return;

  const content = readFileSync(configPath, "utf-8");
  if (!content.includes(PLUGIN_NAME)) return;

  if (configPath.endsWith(".jsonc")) {
    const newContent = content.replace(
      new RegExp(`,?\\s*"${PLUGIN_NAME}"\\s*,?`, "g"),
      (match) => {
        if (match.includes(",")) {
          return match.includes(`"${PLUGIN_NAME}",`) ? "" : "";
        }
        return "";
      }
    ).replace(/\[\s*,/g, "[").replace(/,\s*\]/g, "]");
    writeFileSync(configPath, newContent);
  } else {
    const jsonContent = stripJsoncComments(content);
    const config = JSON.parse(jsonContent);
    if (config.plugin && Array.isArray(config.plugin)) {
      config.plugin = config.plugin.filter((p: string) => p !== PLUGIN_NAME);
      writeFileSync(configPath, JSON.stringify(config, null, 2));
    }
  }

  console.log(`✓ 已从 opencode.json 移除插件`);
}

function registerPluginToPackageJson(): void {
  if (!existsSync(PACKAGE_JSON_FILE)) {
    const packageJson = {
      name: "opencode-plugins",
      private: true,
      dependencies: {
        [PLUGIN_NAME]: `file:./node_modules/${PLUGIN_NAME}`
      }
    };
    writeFileSync(PACKAGE_JSON_FILE, JSON.stringify(packageJson, null, 2));
    console.log(`✓ 已创建 package.json`);
    return;
  }

  const content = readFileSync(PACKAGE_JSON_FILE, "utf-8");
  const packageJson = JSON.parse(content);
  
  if (!packageJson.dependencies) {
    packageJson.dependencies = {};
  }
  
  packageJson.dependencies[PLUGIN_NAME] = `file:./node_modules/${PLUGIN_NAME}`;
  writeFileSync(PACKAGE_JSON_FILE, JSON.stringify(packageJson, null, 2));
  console.log(`✓ 已注册插件到 package.json`);
}

function unregisterPluginFromPackageJson(): void {
  if (!existsSync(PACKAGE_JSON_FILE)) return;

  const content = readFileSync(PACKAGE_JSON_FILE, "utf-8");
  const packageJson = JSON.parse(content);
  
  if (packageJson.dependencies && packageJson.dependencies[PLUGIN_NAME]) {
    delete packageJson.dependencies[PLUGIN_NAME];
    writeFileSync(PACKAGE_JSON_FILE, JSON.stringify(packageJson, null, 2));
    console.log(`✓ 已从 package.json 移除插件`);
  }
}

function createCommands(): void {
  mkdirSync(OPENCODE_COMMAND_DIR, { recursive: true });
  
  const initCommand = `---
description: Initialize Memory Recall with codebase knowledge
---

# Initializing Memory Recall

## Step 1: Import Project Documents

First, import existing documentation:

\`\`\`
memory-recall(mode: "import-docs")
\`\`\`

This imports README.md, CHANGELOG.md, docs/*.md, AGENTS.md etc.

## Step 2: Explore Codebase

Use parallel explore queries:

\`\`\`
Task(explore, "What is the tech stack and dependencies?")
Task(explore, "What is the project structure?")
Task(explore, "How to build, test, and run?")
\`\`\`

## Step 3: Save Knowledge

Use \`memory-recall\` tool for each insight:

\`\`\`
memory-recall(mode: "add", content: "...", type: "project-config", scope: "project")
\`\`\`

**Types:** project-config, architecture, learned-pattern, preference, error-solution
**Scopes:** project (this project), user (cross-project)

## Step 4: Confirm

Tell user what was imported and saved.
`;

  writeFileSync(join(OPENCODE_COMMAND_DIR, "memory-init.md"), initCommand);
  console.log(`✓ 已创建 /memory-init 命令`);
}

function removeCommands(): void {
  const initPath = join(OPENCODE_COMMAND_DIR, "memory-init.md");
  if (existsSync(initPath)) {
    rmSync(initPath);
    console.log(`✓ 已删除 /memory-init 命令`);
  }
}

function configExists(): boolean {
  return existsSync(CONFIG_FILE);
}

function readConfig(): Record<string, unknown> | null {
  if (!existsSync(CONFIG_FILE)) return null;
  try {
    const content = readFileSync(CONFIG_FILE, "utf-8");
    return JSON.parse(stripJsoncComments(content));
  } catch {
    return null;
  }
}

function deleteConfig(): void {
  if (existsSync(CONFIG_FILE)) {
    rmSync(CONFIG_FILE);
    console.log(`✓ 已删除配置文件: ${CONFIG_FILE}`);
  }
}

function writeConfig(config: {
  apiKey: string;
  baseUrl: string;
  userName: string;
  containerTag: string;
}): void {
  const content = `{
  "apiKey": "${config.apiKey}",
  "baseUrl": "${config.baseUrl}",
  "userName": "${config.userName}",
  "userContainerTag": "${config.containerTag}",
  "projectContainerTag": "${config.containerTag}",

  // 检索配置
  "similarityThreshold": 0.3,
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
  "chunksSimilarityThreshold": 0.3,

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

  "language": "auto",
  "logLevel": "info"
}
`;
  mkdirSync(OPENCODE_CONFIG_DIR, { recursive: true });
  writeFileSync(CONFIG_FILE, content);
  console.log(`✓ 配置已保存到 ${CONFIG_FILE}`);
}

async function validateApiKey(baseUrl: string, apiKey: string): Promise<{ valid: boolean; error?: string }> {
  try {
    const response = await fetch(`${baseUrl}/memories?limit=1`, {
      method: "GET",
      headers: {
        "X-API-Key": apiKey,
        "Content-Type": "application/json",
      },
    });

    if (response.ok) return { valid: true };
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
): Promise<{ success: boolean; apiKey?: string; containerTag?: string; error?: string }> {
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
      const data = await response.json();
      return {
        success: true,
        apiKey: data.api_key,
        containerTag: data.container_tag,
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
  console.log("║   Memory Recall OpenCode 插件安装向导     ║");
  console.log("╚════════════════════════════════════════════╝\n");

  const rl = createReadline();

  try {
    console.log("【步骤 1/4】安装插件文件\n");
    const installResult = installPluginFiles();
    if (!installResult.success) {
      console.log(`✗ ${installResult.error}`);
      return;
    }

    console.log("\n【步骤 2/4】注册插件\n");
    registerPluginToOpencode();
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
        
        const reconfigure = await confirm(rl, "\n是否重新配置? (y/n)");
        if (!reconfigure) {
          console.log("\n╔════════════════════════════════════════════╗");
          console.log("║              安装完成！                    ║");
          console.log("╚════════════════════════════════════════════╝");
          console.log("\n下一步:");
          console.log("  1. 确保 Memory Recall API 服务正在运行");
          console.log("  2. 重启 OpenCode\n");
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
    let containerTag: string;

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
      containerTag = result.containerTag!;

      console.log("\n╔════════════════════════════════════════════╗");
      console.log("║              注册成功！                    ║");
      console.log("╚════════════════════════════════════════════╝");
      console.log(`\n  API Key: ${apiKey}`);
      console.log(`  Container: ${containerTag}`);
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
      userName = await questionWithDefault(rl, "请输入用户名", "User");
      containerTag = userName.toLowerCase().replace(/\s+/g, "_");
    }

    writeConfig({ apiKey, baseUrl, userName, containerTag });

    console.log("\n╔════════════════════════════════════════════╗");
    console.log("║              安装完成！                    ║");
    console.log("╚════════════════════════════════════════════╝");
    console.log("\n下一步:");
    console.log("  1. 确保 Memory Recall API 服务正在运行");
    console.log("  2. 重启 OpenCode");
    console.log("  3. 使用 /memory-init 初始化项目记忆\n");

  } finally {
    rl.close();
  }
}

async function doUninstall(): Promise<void> {
  console.log("\n╔════════════════════════════════════════════╗");
  console.log("║   Memory Recall OpenCode 插件卸载         ║");
  console.log("╚════════════════════════════════════════════╝\n");

  const rl = createReadline();

  try {
    if (!configExists() && !existsSync(PLUGIN_INSTALL_DIR)) {
      console.log("未检测到已安装的插件，无需卸载。\n");
      return;
    }

    const existingConfig = readConfig();
    if (existingConfig) {
      console.log("当前配置:");
      console.log(`  API 地址: ${existingConfig.baseUrl || '未设置'}`);
      console.log(`  用户名: ${existingConfig.userName || '未设置'}`);
    }

    const confirmUninstall = await confirm(rl, "\n确定要卸载插件吗? (y/n)");
    if (!confirmUninstall) {
      console.log("\n卸载已取消。");
      return;
    }

    console.log("\n正在卸载...\n");
    
    deleteConfig();
    removeCommands();
    unregisterPluginFromOpencode();
    unregisterPluginFromPackageJson();
    uninstallPluginFiles();

    console.log("\n╔════════════════════════════════════════════╗");
    console.log("║              卸载完成！                    ║");
    console.log("╚════════════════════════════════════════════╝");
    console.log("\n如需重新安装，请运行:");
    console.log("  node dist/cli.js install\n");

  } finally {
    rl.close();
  }
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
  unregisterPluginFromPackageJson();
  uninstallPluginFiles();

  console.log("");
  await doInstall();
}

function printHelp(): void {
  console.log(`
Memory Recall OpenCode 插件

用法:
  node dist/cli.js install    安装插件
  node dist/cli.js uninstall  卸载插件
  node dist/cli.js reinstall  重新安装
  node dist/cli.js status     查看状态
  node dist/cli.js --help     显示帮助

配置文件:
  ~/.config/opencode/memory-recall.jsonc
`);
}

async function showStatus(): Promise<void> {
  console.log("\n=== Memory Recall 插件状态 ===\n");

  if (existsSync(PLUGIN_INSTALL_DIR)) {
    console.log(`✓ 插件已安装: ${PLUGIN_INSTALL_DIR}`);
  } else {
    console.log("✗ 插件未安装");
  }

  const configPath = findOpencodeConfig();
  if (configPath) {
    const content = readFileSync(configPath, "utf-8");
    if (content.includes(PLUGIN_NAME)) {
      console.log("✓ 插件已在 opencode.json 中注册");
    } else {
      console.log("✗ 插件未在 opencode.json 中注册");
    }
  }

  if (existsSync(PACKAGE_JSON_FILE)) {
    const content = readFileSync(PACKAGE_JSON_FILE, "utf-8");
    if (content.includes(PLUGIN_NAME)) {
      console.log("✓ 插件已在 package.json 中注册");
    }
  }

  const config = readConfig();
  if (config?.apiKey) {
    console.log(`\n✓ API 已配置`);
    console.log(`  地址: ${config.baseUrl || '未设置'}`);
    console.log(`  用户: ${config.userName || '未设置'}`);
  } else {
    console.log("\n✗ API 未配置");
  }

  const initPath = join(OPENCODE_COMMAND_DIR, "memory-init.md");
  if (existsSync(initPath)) {
    console.log("\n✓ /memory-init 命令可用");
  }

  console.log("");
}

async function main(): Promise<void> {
  const args = process.argv.slice(2);
  const command = args[0] || "install";

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
      console.log(`未知命令: ${command}`);
      printHelp();
      process.exit(1);
  }
}

main().catch((error) => {
  console.error("执行出错:", error);
  process.exit(1);
});
