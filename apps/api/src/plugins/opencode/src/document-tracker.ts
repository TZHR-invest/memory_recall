import * as fs from "fs";
import * as path from "path";
import * as crypto from "crypto";
import type { ApiClient } from "./client";
import type { Config } from "./config";

interface TrackedDocument {
  path: string;
  hash: string;
  documentId?: string;
  lastModified: number;
}

interface TrackerState {
  initializedAt?: string;
  documents: Record<string, TrackedDocument>;
}

export class DocumentTracker {
  private client: ApiClient;
  private config: Config;
  private directory: string;
  private trackedDocuments: Map<string, TrackedDocument> = new Map();
  private initializedAt: string | null = null;
  private stateFilePath: string;

  constructor(client: ApiClient, config: Config, directory: string) {
    this.client = client;
    this.config = config;
    this.directory = directory;
    this.stateFilePath = path.join(directory, ".memory-recall-docs.json");
    this.loadState();
  }

  isInitialized(): boolean {
    return this.initializedAt !== null;
  }

  getInitializedAt(): string | null {
    return this.initializedAt;
  }

  getDirectory(): string {
    return this.directory;
  }

  /**
   * 获取需要导入的文档列表（排除已追踪的）
   */
  getPendingFiles(): string[] {
    const files = this.scanDirectory();
    return files.filter(filePath => {
      const relativePath = path.relative(this.directory, filePath);
      return !this.trackedDocuments.has(relativePath);
    });
  }

  /**
   * 处理单个文档导入（供队列调用）
   */
  async importSingleFile(filePath: string, timeoutMs?: number): Promise<{ success: boolean; relativePath: string }> {
    const relativePath = path.isAbsolute(filePath) 
      ? path.relative(this.directory, filePath) 
      : filePath;
    const absolutePath = path.isAbsolute(filePath) 
      ? filePath 
      : path.join(this.directory, filePath);

    const result = await this.importFile(absolutePath, timeoutMs);
    
    if (result) {
      this.saveState();
    }

    return { success: result, relativePath };
  }

  /**
   * Scan directory for matching documents and import them to memory storage.
   * Skips already-tracked documents unless clearState() was called.
   * Returns the number of documents imported.
   */
  async scanAndMemorize(timeoutMs?: number): Promise<number> {
    const files = this.scanDirectory();
    let importedCount = 0;

    for (const filePath of files) {
      try {
        const relativePath = path.relative(this.directory, filePath);
        const alreadyTracked = this.trackedDocuments.has(relativePath);

        if (!alreadyTracked) {
          const result = await this.importFile(filePath, timeoutMs);
          if (result) {
            importedCount++;
          }
        }
      } catch (e) {
        console.error(`Failed to import ${filePath}:`, e);
      }
    }

    if (importedCount > 0 || !this.initializedAt) {
      this.initializedAt = new Date().toISOString();
      this.saveState();
    }

    return importedCount;
  }

  /**
   * Force re-scan all documents, re-importing changed files.
   * Use this when documents may have been updated externally.
   */
  async forceRescan(timeoutMs?: number): Promise<number> {
    const files = this.scanDirectory();
    let importedCount = 0;

    for (const filePath of files) {
      try {
        const result = await this.importFile(filePath, timeoutMs);
        if (result) {
          importedCount++;
        }
      } catch (e) {
        console.error(`Failed to import ${filePath}:`, e);
      }
    }

    this.saveState();
    return importedCount;
  }

  /**
   * Track a single file (import or re-import if changed).
   */
  async trackFile(filePath: string): Promise<void> {
    await this.importFile(filePath);
    this.saveState();
  }

  /**
   * Check if a file has changed (for FileWatcher).
   * Returns true if file is new or hash differs from tracked version.
   */
  hasFileChanged(filePath: string): boolean {
    const absolutePath = path.isAbsolute(filePath)
      ? filePath
      : path.join(this.directory, filePath);

    if (!fs.existsSync(absolutePath)) {
      return false;
    }

    const content = fs.readFileSync(absolutePath, "utf-8");
    if (!content.trim()) {
      return false;
    }

    const hash = this.computeHash(content);
    const relativePath = path.relative(this.directory, absolutePath);
    const tracked = this.trackedDocuments.get(relativePath);

    return !tracked || tracked.hash !== hash;
  }

  /**
   * Check if a file has changed and re-import if needed.
   * Called by FileWatcher on file changes.
   */
  async checkFile(filePath: string): Promise<boolean> {
    const absolutePath = path.isAbsolute(filePath)
      ? filePath
      : path.join(this.directory, filePath);

    if (!fs.existsSync(absolutePath)) {
      return false;
    }

    const content = fs.readFileSync(absolutePath, "utf-8");
    const hash = this.computeHash(content);
    const relativePath = path.relative(this.directory, absolutePath);
    const tracked = this.trackedDocuments.get(relativePath);

    // File is new or changed
    if (!tracked || tracked.hash !== hash) {
      return await this.importFile(absolutePath);
    }

    return false;
  }

  /**
   * Scan directory for files matching trackedDocPatterns.
   */
  private scanDirectory(): string[] {
    const files: string[] = [];
    const patterns = this.config.trackedDocPatterns;

    const scanDir = (dir: string) => {
      if (!fs.existsSync(dir)) return;

      const entries = fs.readdirSync(dir, { withFileTypes: true });

      for (const entry of entries) {
        const fullPath = path.join(dir, entry.name);

        // Skip hidden directories and common ignore patterns
        if (entry.isDirectory()) {
          if (
            entry.name.startsWith(".") ||
            entry.name === "node_modules" ||
            entry.name === "__pycache__" ||
            entry.name === "venv" ||
            entry.name === ".venv"
          ) {
            continue;
          }
          scanDir(fullPath);
        } else if (entry.isFile()) {
          // Use relative path for pattern matching to support patterns like "docs/*.md"
          const relativePath = path.relative(this.directory, fullPath);
          if (this.matchesPattern(relativePath, patterns)) {
            files.push(fullPath);
          }
        }
      }
    };

    scanDir(this.directory);
    return files;
  }

  /**
   * Check if a path (relative to project root) matches any of the patterns.
   * Supported patterns:
   * - STAR.md (wildcard suffix) - matches any file ending with .md at any level
   * - docs/STAR.md - matches .md files directly under docs/
   * - docs/STARSTAR/STAR.md - matches .md files anywhere under docs/
   * - READMESTAR.md - matches files starting with README at root level
   * - AGENTS.md - exact match at root level
   * (Note: STAR represents asterisk character to avoid parsing issues)
   */
  private matchesPattern(relativePath: string, patterns: string[]): boolean {
    // Normalize path separators to forward slashes for consistent matching
    const normalizedPath = relativePath.split(path.sep).join("/");
    const filename = path.basename(relativePath);

    for (const pattern of patterns) {
      // Pattern like "*.md" - match filename at any level
      if (pattern.startsWith("*")) {
        const suffix = pattern.slice(1);
        if (filename.endsWith(suffix)) {
          return true;
        }
        continue;
      }

      // Pattern with path separator - match full relative path
      if (pattern.includes("/")) {
        // Handle "docs/**/*.md" -> matches any .md under docs/
        if (pattern.includes("**")) {
          const regexPattern = pattern
            .replace(/\./g, "\\.")
            .replace(/\*\*/g, "<<<DOUBLE_STAR>>>")
            .replace(/\*/g, "[^/]*")
            .replace(/<<<DOUBLE_STAR>>>/g, ".*");
          const regex = new RegExp("^" + regexPattern + "$");
          if (regex.test(normalizedPath)) {
            return true;
          }
        } else {
          // Handle "docs/*.md" -> matches .md directly under docs/
          const escaped = pattern.replace(/\./g, "\\.");
          const regex = new RegExp(
            "^" + escaped.replace(/\*/g, "[^/]*") + "$"
          );
          if (regex.test(normalizedPath)) {
            return true;
          }
        }
        continue;
      }

      // Pattern like "README*.md" - match filename at root level only
      if (pattern.includes("*")) {
        // Only match if file is at root level (no path separator)
        if (!normalizedPath.includes("/")) {
          const escaped = pattern.replace(/\./g, "\\.");
          const regex = new RegExp("^" + escaped.replace(/\*/g, ".*") + "$");
          if (regex.test(filename)) {
            return true;
          }
        }
        continue;
      }

      // Exact match - only at root level
      if (!normalizedPath.includes("/") && filename === pattern) {
        return true;
      }
    }
    return false;
  }

  /**
   * Import a single file to memory storage.
   * Returns true if imported, false if skipped (e.g., duplicate).
   */
  private async importFile(filePath: string, timeoutMs?: number): Promise<boolean> {
    if (!fs.existsSync(filePath)) {
      return false;
    }

    const content = fs.readFileSync(filePath, "utf-8");
    if (!content.trim()) {
      return false;
    }

    const hash = this.computeHash(content);
    const relativePath = path.relative(this.directory, filePath);

    // Check if file is already tracked with same hash
    const tracked = this.trackedDocuments.get(relativePath);
    if (tracked && tracked.hash === hash) {
      return false; // Already imported, no changes
    }

    // Determine document type from extension
    const ext = path.extname(filePath).toLowerCase();
    const docType = this.getDocType(ext);

    // Extract title from first heading or filename
    const title = this.extractTitle(content, path.basename(filePath));

    try {
      const result = await this.client.addDocument(
        content,
        this.client.getProjectTag(),
        {
          title,
          source: relativePath,
          docType,
          metadata: {
            originalPath: relativePath,
            importedAt: new Date().toISOString(),
            fileSize: content.length,
          },
        },
        timeoutMs
      );

      // Update tracking state
      this.trackedDocuments.set(relativePath, {
        path: relativePath,
        hash,
        documentId: result.id,
        lastModified: Date.now(),
      });

      return !result.isDuplicate;
    } catch (e) {
      console.error(`Failed to import document ${relativePath}:`, e);
      throw e;
    }
  }

  /**
   * Compute SHA-256 hash of content.
   */
  private computeHash(content: string): string {
    return crypto.createHash("sha256").update(content).digest("hex");
  }

  /**
   * Get document type from file extension.
   */
  private getDocType(ext: string): string {
    const typeMap: Record<string, string> = {
      ".md": "markdown",
      ".markdown": "markdown",
      ".txt": "text",
      ".rst": "rst",
      ".adoc": "asciidoc",
      ".py": "code",
      ".ts": "code",
      ".js": "code",
      ".go": "code",
      ".rs": "code",
      ".java": "code",
      ".c": "code",
      ".cpp": "code",
      ".h": "code",
      ".json": "config",
      ".yaml": "config",
      ".yml": "config",
      ".toml": "config",
    };
    return typeMap[ext] || "text";
  }

  /**
   * Extract title from content (first heading) or fallback to filename.
   */
  private extractTitle(content: string, filename: string): string {
    // Try to find first markdown heading
    const headingMatch = content.match(/^#\s+(.+)$/m);
    if (headingMatch) {
      return headingMatch[1].trim();
    }

    // Fallback to filename without extension
    return filename.replace(/\.[^.]+$/, "");
  }

  /**
   * Load tracking state from disk.
   */
  private loadState(): void {
    try {
      if (fs.existsSync(this.stateFilePath)) {
        const data = fs.readFileSync(this.stateFilePath, "utf-8");
        const state = JSON.parse(data) as TrackerState;
        this.trackedDocuments = new Map(Object.entries(state.documents || {}));
        this.initializedAt = state.initializedAt || null;
      }
    } catch {
      this.trackedDocuments = new Map();
      this.initializedAt = null;
    }
  }

  private saveState(): void {
    try {
      const state: TrackerState = {
        initializedAt: this.initializedAt || undefined,
        documents: Object.fromEntries(this.trackedDocuments),
      };
      fs.writeFileSync(this.stateFilePath, JSON.stringify(state, null, 2));
    } catch {}
  }

  /**
   * Get list of tracked documents.
   */
  getTrackedDocuments(): TrackedDocument[] {
    return Array.from(this.trackedDocuments.values());
  }

  /**
   * Clear tracking state and reset initialization flag.
   * Next scan will treat this as first run.
   */
  clearState(): void {
    this.trackedDocuments.clear();
    this.initializedAt = null;
    try {
      if (fs.existsSync(this.stateFilePath)) {
        fs.unlinkSync(this.stateFilePath);
      }
    } catch {}
  }
}
