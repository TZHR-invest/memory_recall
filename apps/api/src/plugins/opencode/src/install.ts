#!/usr/bin/env bun
/**
 * Memory Recall OpenCode Plugin - Installation Script
 * 
 * Usage:
 *   bunx memory-recall-opencode install    - 安装插件
 *   bunx memory-recall-opencode uninstall  - 卸载插件
 *   bunx memory-recall-opencode reinstall  - 重新安装
 */

import * as fs from "fs";
import * as path from "path";
import * as os from "os";
import * as readline from "readline";

// ============================================================================
// Types
// ============================================================================

interface Config {
  apiKey: string;
  baseUrl: string;
  userName: string;
  userContainerTag: string | null;
  projectContainerTag: string | null;
  similarityThreshold: number;
  maxMemories: number;
  maxProjectMemories: number;
  injectProfile: boolean;
  compactionThreshold: number;
  enableSummaryCapture: boolean;
  enableDocumentTracking: boolean;
  trackedDocPatterns: string[];
  language: "auto" | "zh_CN" | "en_US";
  logLevel: "debug" | "info" | "warn" | "error";
  enableChunksSearch: boolean;
  maxChunks: number;
  chunksSimilarityThreshold: number;
  enableGraphRecall: boolean;
  enableEntityRecall: boolean;
  graphMaxDepth: number;
  graphMaxNodes: number;
  injectionStrategy: "once" | "smart" | "always";
  initialInjection: {
    profile: boolean;
    projectMemories: boolean;
    chunks: boolean;
    maxChunks: number;
  };
  smartRecall: {
    enabled: boolean;
    keywords: string[];
    maxAdditionalMemories: number;
    maxAdditionalChunks: number;
  };
}

interface InitializeResponse {
  api_key: string;
  key_id: string;
  user_id: string;
  user_name: string;
  container_tag: string;
  config_example: Record<string, unknown>;
}

// ============================================================================
// Constants
// ============================================================================

const DEFAULT_BASE_URL = "http://localhost:8000";
const CONFIG_DIR = ".config";
const OPENCODE_DIR = "opencode";
const CONFIG_FILE = "memory-recall.jsonc";

const DEFAULT_CONFIG: Omit<Config, "apiKey"> = {
  baseUrl: DEFAULT_BASE_URL,
  userName: "User",
  userContainerTag: null,
  projectContainerTag: null,
  similarityThreshold: 0.6,
  maxMemories: 5,
  maxProjectMemories: 10,
  injectProfile: true,
  compactionThreshold: 0.8,
  enableSummaryCapture: true,
  enableDocumentTracking: true,
  trackedDocPatterns: [
    "README*.md",
    "CHANGELOG*.md",
    "docs/*.md",
    "AGENTS.md",
  ],
  language: "auto",
  logLevel: "info",
  enableChunksSearch: true,
  maxChunks: 5,
  chunksSimilarityThreshold: 0.5,
  enableGraphRecall: true,
  enableEntityRecall: true,
  graphMaxDepth: 2,
  graphMaxNodes: 5,
  injectionStrategy: "smart",
  initialInjection: {
    profile: true,
    projectMemories: true,
    chunks: true,
    maxChunks: 3,
  },
  smartRecall: {
    enabled: true,
    keywords: ["记得", "之前", "上次", "以前", "回忆", "记忆", "recall", "remember", "previous", "earlier"],
    maxAdditionalMemories: 3,
    maxAdditionalChunks: 2,
  },
};

// ============================================================================
// Utility Functions
// ============================================================================

function getConfigPath(): string {
  return path.join(os.homedir(), CONFIG_DIR, OPENCODE_DIR, CONFIG_FILE);
}

function getConfigDir(): string {
  return path.join(os.homedir(), CONFIG_DIR, OPENCODE_DIR);
}

function ensureConfigDir(): void {
  const configDir = getConfigDir();
  if (!fs.existsSync(configDir)) {
    fs.mkdirSync(configDir, { recursive: true });
    console.log(`✓ 创建配置目录: ${configDir}`);
  }
}

function parseJsonc(content: string): Record<string, unknown> {
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

  const restored = withoutComments.replace(
    new RegExp(`${STRING_PLACEHOLDER_PREFIX}(\\d+)__`, "g"),
    (_, idx) => protectedStrings[parseInt(idx)]
  );

  try {
    return JSON.parse(restored);
  } catch {
    return {};
  }
}

function readExistingConfig(): Config | null {
  const configPath = getConfigPath();
  if (!fs.existsSync(configPath)) {
    return null;
  }

  try {
    const content = fs.readFileSync(configPath, "utf-8");
    const parsed = parseJsonc(content);
    
    return {
      ...DEFAULT_CONFIG,
      ...parsed,
    } as Config;
  } catch (error) {
    console.error(`读取配置文件失败: ${error}`);
    return null;
  }
}

function configExists(): boolean {
  return fs.existsSync(getConfigPath());
}

function deleteConfig(): boolean {
  const configPath = getConfigPath();
  if (fs.existsSync(configPath)) {
    fs.unlinkSync(configPath);
    console.log(`✓ 已删除配置文件: ${configPath}`);
    return true;
  }
  return false;
}

function writeConfig(config: Config): void {
  ensureConfigDir();
  const configPath = getConfigPath();
  
  const content = `{
    "apiKey": "${config.apiKey}",
    "baseUrl": "${config.baseUrl}",
    "userName": "${config.userName}",

    // 容器标签配置 - 使用 API Key 对应的容器
    "userContainerTag": ${config.userContainerTag ? `"${config.userContainerTag}"` : "null"},
    "projectContainerTag": ${config.projectContainerTag ? `"${config.projectContainerTag}"` : "null"},

    // 检索配置
    "similarityThreshold": ${config.similarityThreshold},
    "maxMemories": ${config.maxMemories},
    "maxProjectMemories": ${config.maxProjectMemories},
    "injectProfile": ${config.injectProfile},
    
    // 文档/Chunks 召回配置
    "enableChunksSearch": ${config.enableChunksSearch},
    "maxChunks": ${config.maxChunks},
    "chunksSimilarityThreshold": ${config.chunksSimilarityThreshold},
    "compactionThreshold": ${config.compactionThreshold},
    "enableSummaryCapture": ${config.enableSummaryCapture},
    "enableDocumentTracking": ${config.enableDocumentTracking},
    "trackedDocPatterns": ${JSON.stringify(config.trackedDocPatterns)},
    "language": "${config.language}",
    "logLevel": "${config.logLevel}"
}
`;

  fs.writeFileSync(configPath, content, "utf-8");
  console.log(`✓ 配置文件已保存: ${configPath}`);
}

// ============================================================================
// Input Functions
// ============================================================================

function createReadlineInterface(): readline.Interface {
  return readline.createInterface({
    input: process.stdin,
    output: process.stdout,
  });
}

function question(rl: readline.Interface, prompt: string): Promise<string> {
  return new Promise((resolve) => {
    rl.question(prompt, (answer) => {
      resolve(answer.trim());
    });
  });
}

function questionWithDefault(rl: readline.Interface, prompt: string, defaultValue: string): Promise<string> {
  return new Promise((resolve) => {
    rl.question(`${prompt} [默认: ${defaultValue}]: `, (answer) => {
      resolve(answer.trim() || defaultValue);
    });
  });
}

async function confirm(rl: readline.Interface, prompt: string): Promise<boolean> {
  const answer = await question(rl, `${prompt} (y/n): `);
  return answer.toLowerCase() === "y" || answer.toLowerCase() === "yes";
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

// ============================================================================
// API Functions
// ============================================================================

async function checkServerHasApiKey(baseUrl: string): Promise<{ hasKey: boolean; error?: string }> {
  try {
    const response = await fetch(`${baseUrl}/auth/initialize`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        plugin_name: "check",
        user_name: "check",
        permissions: ["read"],
      }),
    });

    if (response.ok) {
      return { hasKey: false };
    } else if (response.status === 403) {
      return { hasKey: true };
    } else {
      return { hasKey: true };
    }
  } catch (error) {
    return { hasKey: false, error: `无法连接到服务器: ${error}` };
  }
}

async function validateApiKey(baseUrl: string, apiKey: string): Promise<{ valid: boolean; userId?: string; error?: string }> {
  try {
    const response = await fetch(`${baseUrl}/memories?limit=1`, {
      method: "GET",
      headers: {
        "X-API-Key": apiKey,
        "Content-Type": "application/json",
      },
    });

    if (response.ok) {
      return { valid: true };
    } else if (response.status === 401) {
      return { valid: false, error: "API Key 无效" };
    } else if (response.status === 403) {
      return { valid: false, error: "API Key 无权限" };
    } else {
      return { valid: false, error: `服务器返回错误: ${response.status}` };
    }
  } catch (error) {
    return { valid: false, error: `无法连接到服务器: ${error}` };
  }
}

async function registerNewUser(
  baseUrl: string,
  userName: string,
  apiKeyName: string
): Promise<{ success: boolean; data?: InitializeResponse; error?: string }> {
  try {
    const response = await fetch(`${baseUrl}/auth/initialize`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        plugin_name: apiKeyName,
        user_name: userName,
        permissions: ["read", "write", "delete", "admin"],
      }),
    });

    if (response.ok) {
      const data = (await response.json()) as InitializeResponse;
      return { success: true, data };
    } else if (response.status === 403) {
      return { 
        success: false, 
        error: "已有 API Key 存在，请选择'创建新 API Key'选项使用已有管理员 Key 创建。" 
      };
    } else {
      const errorData = await response.json().catch(() => ({}));
      return { 
        success: false, 
        error: `注册失败: ${response.status} - ${JSON.stringify(errorData)}` 
      };
    }
  } catch (error) {
    return { success: false, error: `无法连接到服务器: ${error}` };
  }
}

async function createNewApiKey(
  baseUrl: string,
  adminApiKey: string,
  keyName: string
): Promise<{ success: boolean; data?: { key: string; id: string }; error?: string }> {
  try {
    const response = await fetch(`${baseUrl}/auth/api-keys`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-API-Key": adminApiKey,
      },
      body: JSON.stringify({
        name: keyName,
        permissions: ["read", "write", "delete", "admin"],
        is_test: false,
      }),
    });

    if (response.ok) {
      const data = await response.json();
      return { success: true, data: { key: data.key, id: data.id } };
    } else if (response.status === 401) {
      return { success: false, error: "管理员 API Key 无效" };
    } else if (response.status === 403) {
      return { success: false, error: "该 API Key 没有 admin 权限" };
    } else {
      const errorData = await response.json().catch(() => ({}));
      return { success: false, error: `创建失败: ${response.status} - ${JSON.stringify(errorData)}` };
    }
  } catch (error) {
    return { success: false, error: `无法连接到服务器: ${error}` };
  }
}

// ============================================================================
// Installation Flows
// ============================================================================

async function existingUserFlow(rl: readline.Interface, baseUrl: string): Promise<Config | null> {
  console.log("\n=== 现有用户配置 ===\n");
  
  const apiKey = await question(rl, "请输入您的 API Key: ");
  if (!apiKey) {
    console.log("API Key 不能为空");
    return null;
  }

  console.log("\n正在验证 API Key...");
  const validation = await validateApiKey(baseUrl, apiKey);
  
  if (!validation.valid) {
    console.log(`✗ API Key 验证失败: ${validation.error}`);
    
    const retry = await confirm(rl, "是否重试?");
    if (retry) {
      return existingUserFlow(rl, baseUrl);
    }
    return null;
  }

  console.log("✓ API Key 验证成功");

  const userName = await questionWithDefault(rl, "请输入您的用户名", "User");

  return {
    ...DEFAULT_CONFIG,
    apiKey,
    baseUrl,
    userName,
  };
}

async function newUserFlow(rl: readline.Interface, baseUrl: string): Promise<Config | null> {
  console.log("\n=== 新用户注册 ===\n");
  
  const userName = await question(rl, "请输入您的用户名 (例如: John Doe): ");
  if (!userName) {
    console.log("用户名不能为空");
    return null;
  }

  const apiKeyName = await questionWithDefault(rl, "请输入 API Key 名称", "memory-recall-plugin");

  console.log(`\n正在连接到 ${baseUrl} 注册新用户...`);
  const result = await registerNewUser(baseUrl, userName, apiKeyName);

  if (!result.success) {
    console.log(`✗ 注册失败: ${result.error}`);
    
    if (result.error?.includes("已有 API Key")) {
      console.log("\n提示: 该服务器已有用户注册，请使用'现有用户'选项。");
    }
    
    const retry = await confirm(rl, "是否重试?");
    if (retry) {
      return newUserFlow(rl, baseUrl);
    }
    return null;
  }

  const data = result.data!;
  
  console.log("\n========================================");
  console.log("✓ 注册成功!");
  console.log("========================================");
  console.log(`\n  API Key: ${data.api_key}`);
  console.log(`  Key ID:  ${data.key_id}`);
  console.log(`  User ID: ${data.user_id}`);
  console.log(`  Container Tag: ${data.container_tag}`);
  console.log("\n⚠️  请妥善保存 API Key，此密钥只会显示一次！");
  console.log("========================================\n");

  return {
    ...DEFAULT_CONFIG,
    apiKey: data.api_key,
    baseUrl,
    userName: data.user_name,
    userContainerTag: data.container_tag,
    projectContainerTag: data.container_tag,
  };
}

async function createNewApiKeyFlow(rl: readline.Interface, baseUrl: string): Promise<Config | null> {
  console.log("\n=== 创建新 API Key ===\n");
  console.log("管理员 API Key 说明:");
  console.log("  - 首次注册时创建的 API Key 默认具有管理员权限");
  console.log("  - 具有 admin 权限的 Key 可以创建新的 API Key");
  console.log("  - 如果您是首次使用此服务器，请选择'首次注册'选项\n");
  
  const adminApiKey = await question(rl, "请输入管理员 API Key: ");
  if (!adminApiKey) {
    console.log("管理员 API Key 不能为空");
    return null;
  }

  const keyName = await questionWithDefault(rl, "请输入新 API Key 名称", "memory-recall-plugin");
  const userName = await questionWithDefault(rl, "请输入用户名", "User");

  console.log(`\n正在创建新 API Key...`);
  const result = await createNewApiKey(baseUrl, adminApiKey, keyName);

  if (!result.success) {
    console.log(`✗ 创建失败: ${result.error}`);
    
    const retry = await confirm(rl, "是否重试?");
    if (retry) {
      return createNewApiKeyFlow(rl, baseUrl);
    }
    return null;
  }

  const data = result.data!;
  
  console.log("\n========================================");
  console.log("✓ API Key 创建成功!");
  console.log("========================================");
  console.log(`\n  API Key: ${data.key}`);
  console.log(`  Key ID:  ${data.id}`);
  console.log(`  Container Tag: ${data.id}`);
  console.log("\n⚠️  请妥善保存 API Key，此密钥只会显示一次！");
  console.log("========================================\n");

  return {
    ...DEFAULT_CONFIG,
    apiKey: data.key,
    baseUrl,
    userName,
    userContainerTag: data.id,
    projectContainerTag: data.id,
  };
}

async function displayConfig(config: Config): Promise<void> {
  console.log("\n=== 配置预览 ===\n");
  console.log(`  API 服务地址: ${config.baseUrl}`);
  console.log(`  用户名: ${config.userName}`);
  console.log(`  API Key: ${config.apiKey.substring(0, 10)}...`);
  console.log(`  容器标签: ${config.userContainerTag || "自动"}`);
  console.log(`  召回阈值: ${config.similarityThreshold}`);
  console.log(`  最大记忆数: ${config.maxMemories}`);
  console.log(`  注入策略: ${config.injectionStrategy}`);
}

async function doInstall(): Promise<void> {
  const rl = createReadlineInterface();

  try {
    if (configExists()) {
      const existingConfig = readExistingConfig();
      console.log("检测到已有配置文件:");
      if (existingConfig) {
        await displayConfig(existingConfig);
      }
      
      console.log("\n请选择操作:");
      console.log("  1. 更新配置 (保留部分设置)");
      console.log("  2. 重新安装 (删除旧配置)");
      console.log("  3. 取消");
      
      const choice = await question(rl, "请选择 (1-3): ");
      
      if (choice === "2") {
        console.log("\n=== 重新安装 ===\n");
        deleteConfig();
      } else if (choice === "3") {
        console.log("\n安装已取消。");
        return;
      }
    }

    // Select user type
    const userTypes = [
      "使用已有 API Key", 
      "创建新 API Key (需要管理员 Key)",
      "首次注册 (仅限服务器无 Key 时)"
    ];

    // Get server URL first
    const baseUrl = await questionWithDefault(rl, "\n请输入 API 服务地址", DEFAULT_BASE_URL);

    // Check server status
    console.log("\n正在检查服务器状态...");
    const serverStatus = await checkServerHasApiKey(baseUrl);
    
    if (serverStatus.error) {
      console.log(`✗ 无法连接到服务器: ${serverStatus.error}`);
      const continueAnyway = await confirm(rl, "是否继续配置?");
      if (!continueAnyway) {
        console.log("\n安装已取消。");
        return;
      }
    } else if (serverStatus.hasKey) {
      console.log("✓ 服务器已有 API Key 注册");
      console.log("\n可用选项:");
      console.log("  1. 使用已有 API Key - 输入您现有的 API Key");
      console.log("  2. 创建新 API Key - 使用首次注册时获得的 Key 创建新 Key");
      console.log("  3. 取消");
      console.log("\n提示: 首次注册时创建的 Key 具有管理员权限，可用于创建新 Key");
      
      const choice = await question(rl, "\n请选择 (1-3): ");
      
      if (choice === "1") {
        const config = await existingUserFlow(rl, baseUrl);
        if (!config) {
          console.log("\n安装已取消。");
          return;
        }
        await displayConfig(config);
        const confirmSave = await confirm(rl, "\n是否保存配置?");
        if (!confirmSave) {
          console.log("\n安装已取消。");
          return;
        }
        writeConfig(config);
        console.log("\n✓ 安装完成！");
        return;
      } else if (choice === "2") {
        const config = await createNewApiKeyFlow(rl, baseUrl);
        if (!config) {
          console.log("\n安装已取消。");
          return;
        }
        await displayConfig(config);
        const confirmSave = await confirm(rl, "\n是否保存配置?");
        if (!confirmSave) {
          console.log("\n安装已取消。");
          return;
        }
        writeConfig(config);
        console.log("\n✓ 安装完成！");
        return;
      } else {
        console.log("\n安装已取消。");
        return;
      }
    } else {
      console.log("✓ 服务器尚未注册，可进行首次注册");
    }

    const selectedType = await selectOption(rl, "请选择用户类型:", userTypes);

    // Run appropriate flow
    let config: Config | null = null;
    
    if (selectedType === 0) {
      config = await existingUserFlow(rl, baseUrl);
    } else if (selectedType === 1) {
      config = await createNewApiKeyFlow(rl, baseUrl);
    } else {
      config = await newUserFlow(rl, baseUrl);
    }

    if (!config) {
      console.log("\n安装已取消。");
      return;
    }

    // Display and confirm
    await displayConfig(config);
    
    const confirmSave = await confirm(rl, "\n是否保存配置?");
    if (!confirmSave) {
      console.log("\n安装已取消。");
      return;
    }

    // Save config
    writeConfig(config);

    console.log("\n========================================");
    console.log("✓ 安装完成!");
    console.log("========================================");
    console.log(`\n配置文件位置: ${getConfigPath()}`);
    console.log("\n下一步:");
    console.log("  1. 确保 Memory Recall API 服务正在运行");
    console.log("  2. 重启 OpenCode 以加载插件");
    console.log("  3. 开始使用记忆功能！\n");

  } finally {
    rl.close();
  }
}

async function doUninstall(): Promise<void> {
  const rl = createReadlineInterface();

  try {
    if (!configExists()) {
      console.log("\n未检测到配置文件，无需卸载。\n");
      return;
    }

    const existingConfig = readExistingConfig();
    console.log("\n=== 卸载 Memory Recall 插件 ===\n");
    if (existingConfig) {
      await displayConfig(existingConfig);
    }

    const confirmUninstall = await confirm(rl, "\n确定要卸载插件配置吗?");
    if (!confirmUninstall) {
      console.log("\n卸载已取消。");
      return;
    }

    deleteConfig();

    console.log("\n========================================");
    console.log("✓ 卸载完成!");
    console.log("========================================");
    console.log("\n如需重新安装，请运行:");
    console.log("  bunx memory-recall-opencode install\n");

  } finally {
    rl.close();
  }
}

async function doReinstall(): Promise<void> {
  console.log("\n=== 重新安装 Memory Recall 插件 ===\n");
  
  if (configExists()) {
    console.log("正在删除旧配置...\n");
    deleteConfig();
  }

  await doInstall();
}

function printHelp(): void {
  console.log(`
Memory Recall OpenCode 插件

用法:
  bun run dist/install.js install    安装插件
  bun run dist/install.js uninstall  卸载插件
  bun run dist/install.js reinstall  重新安装
  bun run dist/install.js --help     显示帮助

用户类型选项:
  1. 使用已有 API Key - 直接使用现有的 API Key
  2. 创建新 API Key - 使用管理员 Key 创建新的 API Key
  3. 首次注册 - 仅限服务器没有任何 API Key 时

配置文件位置:
  ~/.config/opencode/memory-recall.jsonc
`);
}

// ============================================================================
// Main
// ============================================================================

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
      console.log("\n========================================");
      console.log("  Memory Recall OpenCode 插件卸载");
      console.log("========================================\n");
      await doUninstall();
      break;
    case "reinstall":
    case "r":
      await doReinstall();
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
