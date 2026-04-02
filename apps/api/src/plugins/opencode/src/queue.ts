/**
 * 异步任务队列 - 纯内存版本（v1）
 * 
 * 功能：
 * - 任务异步执行，不阻塞工具调用
 * - 并发控制（默认 3 个并发）
 * - 自动重试（指数退避）
 * - 任务状态追踪
 */

import { randomUUID } from "crypto";

/**
 * 任务类型
 */
export type TaskType = "add" | "import-doc";

/**
 * 任务状态
 */
export type TaskStatus = "pending" | "running" | "success" | "failed";

/**
 * 任务接口
 */
export interface Task {
  id: string;
  type: TaskType;
  payload: TaskPayload;
  status: TaskStatus;
  retryCount: number;
  maxRetries: number;
  error?: string;
  errorHistory?: ErrorRecord[];
  createdAt: number;
  updatedAt: number;
  startedAt?: number;
  completedAt?: number;
}

/**
 * 任务载荷
 */
export interface TaskPayload {
  // add mode
  content?: string;
  containerTag?: string;
  isStatic?: boolean;
  memoryType?: string;
  
  // import-doc mode
  filePath?: string;
  relativePath?: string;
}

/**
 * 错误记录
 */
export interface ErrorRecord {
  timestamp: number;
  error: string;
  retryCount: number;
}

/**
 * 任务执行器
 */
export type TaskExecutor = (task: Task) => Promise<Record<string, unknown> | void>;

/**
 * 重试策略配置
 */
export interface RetryPolicyConfig {
  maxRetries: number;
  initialDelay: number;
  maxDelay: number;
  backoffMultiplier: number;
}

/**
 * 默认重试策略
 */
const DEFAULT_RETRY_POLICY: RetryPolicyConfig = {
  maxRetries: 3,
  initialDelay: 1000,
  maxDelay: 10000,
  backoffMultiplier: 2,
};

/**
 * 队列配置
 */
export interface QueueConfig {
  maxConcurrency: number;
  maxSize: number;
  retryPolicy: RetryPolicyConfig;
}

/**
 * 默认队列配置
 */
const DEFAULT_QUEUE_CONFIG: QueueConfig = {
  maxConcurrency: 3,
  maxSize: 100,
  retryPolicy: DEFAULT_RETRY_POLICY,
};

/**
 * 计算重试延迟（指数退避）
 */
export function calculateRetryDelay(
  retryCount: number,
  policy: RetryPolicyConfig
): number {
  const delay = policy.initialDelay * Math.pow(policy.backoffMultiplier, retryCount);
  return Math.min(delay, policy.maxDelay);
}

/**
 * 任务队列类
 */
export class TaskQueue {
  private tasks: Map<string, Task> = new Map();
  private pendingQueue: string[] = [];
  private runningCount: number = 0;
  private config: QueueConfig;
  private executor: TaskExecutor | null = null;
  private processingInterval: ReturnType<typeof setInterval> | null = null;

  constructor(config: Partial<QueueConfig> = {}) {
    this.config = { ...DEFAULT_QUEUE_CONFIG, ...config };
    
    // 合并重试策略
    if (config.retryPolicy) {
      this.config.retryPolicy = { ...DEFAULT_RETRY_POLICY, ...config.retryPolicy };
    }
  }

  /**
   * 设置任务执行器
   */
  setExecutor(executor: TaskExecutor): void {
    this.executor = executor;
  }

  /**
   * 入队任务
   */
  enqueue(type: TaskType, payload: TaskPayload): string {
    // 检查队列大小
    if (this.tasks.size >= this.config.maxSize) {
      throw new Error("Queue is full");
    }

    const task: Task = {
      id: `task_${randomUUID()}`,
      type,
      payload,
      status: "pending",
      retryCount: 0,
      maxRetries: this.config.retryPolicy.maxRetries,
      createdAt: Date.now(),
      updatedAt: Date.now(),
    };

    this.tasks.set(task.id, task);
    this.pendingQueue.push(task.id);

    return task.id;
  }

  /**
   * 获取任务状态
   */
  getStatus(taskId: string): Task | null {
    return this.tasks.get(taskId) || null;
  }

  /**
   * 获取所有任务
   */
  getAllTasks(): Task[] {
    return Array.from(this.tasks.values());
  }

  /**
   * 获取待处理任务数
   */
  getPendingCount(): number {
    return this.pendingQueue.length;
  }

  /**
   * 获取正在执行任务数
   */
  getRunningCount(): number {
    return this.runningCount;
  }

  /**
   * 获取队列大小
   */
  getSize(): number {
    return this.tasks.size;
  }

  /**
   * 启动队列处理
   */
  start(): void {
    if (this.processingInterval) {
      return; // 已经在运行
    }

    // 每 100ms 检查一次是否有空闲槽位
    this.processingInterval = setInterval(() => {
      this.processNext();
    }, 100);
  }

  /**
   * 停止队列处理
   */
  stop(): void {
    if (this.processingInterval) {
      clearInterval(this.processingInterval);
      this.processingInterval = null;
    }
  }

  /**
   * 处理下一个任务
   */
  private async processNext(): Promise<void> {
    // 检查是否有空闲槽位
    if (this.runningCount >= this.config.maxConcurrency) {
      return;
    }

    // 检查是否有待处理任务
    if (this.pendingQueue.length === 0) {
      return;
    }

    // 检查执行器是否已设置
    if (!this.executor) {
      return;
    }

    // 取出下一个任务
    const taskId = this.pendingQueue.shift();
    if (!taskId) {
      return;
    }

    const task = this.tasks.get(taskId);
    if (!task) {
      return;
    }

    // 执行任务
    await this.executeTask(task);
  }

  /**
   * 执行单个任务
   */
  private async executeTask(task: Task): Promise<void> {
    if (!this.executor) {
      return;
    }

    // 更新状态为 running
    task.status = "running";
    task.startedAt = Date.now();
    task.updatedAt = Date.now();
    this.runningCount++;

    try {
      // 执行任务
      await this.executor(task);

      // 成功
      task.status = "success";
      task.completedAt = Date.now();
      task.updatedAt = Date.now();
    } catch (e) {
      // 失败
      const errorMsg = e instanceof Error ? e.message : String(e);
      task.error = errorMsg;
      task.updatedAt = Date.now();

      // 记录错误历史
      if (!task.errorHistory) {
        task.errorHistory = [];
      }
      task.errorHistory.push({
        timestamp: Date.now(),
        error: errorMsg,
        retryCount: task.retryCount,
      });

      // 检查是否可以重试
      if (task.retryCount < task.maxRetries) {
        // 重新入队等待重试
        task.retryCount++;
        task.status = "pending";
        
        // 计算延迟
        const delay = calculateRetryDelay(task.retryCount, this.config.retryPolicy);
        
        // 延迟后重新入队
        setTimeout(() => {
          this.pendingQueue.push(task.id);
        }, delay);
      } else {
        // 达到最大重试次数，标记为失败
        task.status = "failed";
        task.completedAt = Date.now();
      }
    } finally {
      this.runningCount--;
    }
  }

  /**
   * 手动重试任务
   */
  retry(taskId: string): boolean {
    const task = this.tasks.get(taskId);
    if (!task) {
      return false;
    }

    // 只有失败的任务可以重试
    if (task.status !== "failed") {
      return false;
    }

    // 重置重试次数
    task.retryCount = 0;
    task.status = "pending";
    task.error = undefined;
    task.updatedAt = Date.now();

    // 加入队列
    this.pendingQueue.push(task.id);

    return true;
  }

  /**
   * 清理已完成的任务
   */
  clearCompleted(): number {
    let cleared = 0;
    for (const [id, task] of this.tasks) {
      if (task.status === "success" || task.status === "failed") {
        this.tasks.delete(id);
        cleared++;
      }
    }
    return cleared;
  }

  /**
   * 清空队列
   */
  clear(): void {
    this.tasks.clear();
    this.pendingQueue = [];
    this.runningCount = 0;
  }
}
