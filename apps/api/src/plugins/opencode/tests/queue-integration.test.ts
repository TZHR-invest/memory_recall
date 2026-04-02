import { describe, test, expect, beforeEach, afterEach } from "bun:test";
import { TaskQueue } from "../src/queue";

describe("Queue Integration Tests", () => {
  let queue: TaskQueue;

  beforeEach(() => {
    queue = new TaskQueue();
  });

  afterEach(() => {
    queue.stop();
  });

  describe("端到端流程", () => {
    test("完整的任务生命周期：入队 -> 执行 -> 成功", async () => {
      const results: string[] = [];
      
      queue.setExecutor(async (task) => {
        results.push(task.payload.content as string);
        return { processed: true };
      });
      
      queue.start();
      
      const taskId = queue.enqueue("add", { content: "test memory" });
      
      // 等待处理间隔（100ms）+ 执行时间
      await new Promise(resolve => setTimeout(resolve, 200));
      
      const task = queue.getStatus(taskId);
      expect(task!.status).toBe("success");
      expect(results).toContain("test memory");
    });

    test("多个任务顺序执行", async () => {
      const order: number[] = [];
      
      queue.setExecutor(async (task) => {
        order.push(task.payload.content as number);
        return {};
      });
      
      queue.start();
      
      queue.enqueue("add", { content: 1 });
      queue.enqueue("add", { content: 2 });
      queue.enqueue("add", { content: 3 });
      
      await new Promise(resolve => setTimeout(resolve, 500));
      
      expect(order).toEqual([1, 2, 3]);
    });
  });

  describe("失败重试场景", () => {
    test("间歇性失败最终成功", async () => {
      const retryQueue = new TaskQueue({ 
        maxConcurrency: 1,
        retryPolicy: { maxRetries: 3, initialDelay: 30, maxDelay: 100, backoffMultiplier: 2 }
      });
      
      let attempts = 0;
      
      retryQueue.setExecutor(async () => {
        attempts++;
        if (attempts < 3) {
          throw new Error("Temporary failure");
        }
        return { success: true };
      });
      
      retryQueue.start();
      
      const taskId = retryQueue.enqueue("add", { content: "test" });
      
      // 初始执行 + 重试延迟 + 处理间隔
      await new Promise(resolve => setTimeout(resolve, 500));
      
      const task = retryQueue.getStatus(taskId);
      expect(task!.status).toBe("success");
      expect(attempts).toBe(3);
      
      retryQueue.stop();
    });

    test("持续失败最终标记为 failed", async () => {
      const retryQueue = new TaskQueue({ 
        maxConcurrency: 1,
        retryPolicy: { maxRetries: 2, initialDelay: 30, maxDelay: 100, backoffMultiplier: 2 }
      });
      
      retryQueue.setExecutor(async () => {
        throw new Error("Permanent failure");
      });
      
      retryQueue.start();
      
      const taskId = retryQueue.enqueue("add", { content: "test" });
      
      // 初始执行 + 重试延迟 + 处理间隔
      await new Promise(resolve => setTimeout(resolve, 600));
      
      const task = retryQueue.getStatus(taskId);
      expect(task!.status).toBe("failed");
      expect(task!.error).toBe("Permanent failure");
      
      retryQueue.stop();
    });
  });

  describe("并发场景", () => {
    test("并发限制生效", async () => {
      const concurrencyQueue = new TaskQueue({ maxConcurrency: 2 });
      let maxConcurrent = 0;
      let currentConcurrent = 0;
      
      concurrencyQueue.setExecutor(async () => {
        currentConcurrent++;
        maxConcurrent = Math.max(maxConcurrent, currentConcurrent);
        await new Promise(resolve => setTimeout(resolve, 50));
        currentConcurrent--;
        return {};
      });
      
      concurrencyQueue.start();
      
      for (let i = 0; i < 5; i++) {
        concurrencyQueue.enqueue("add", { content: i });
      }
      
      await new Promise(resolve => setTimeout(resolve, 300));
      
      expect(maxConcurrent).toBeLessThanOrEqual(2);
      
      concurrencyQueue.stop();
    });
  });
});

describe("Performance Tests", () => {
  test("入队响应时间 < 10ms", async () => {
    const queue = new TaskQueue();
    queue.setExecutor(async () => ({}));
    
    const start = performance.now();
    const taskId = queue.enqueue("add", { content: "test" });
    const duration = performance.now() - start;
    
    expect(duration).toBeLessThan(10);
    expect(taskId).toMatch(/^task_/);
    
    queue.stop();
  });

  test("状态查询响应时间 < 5ms", async () => {
    const queue = new TaskQueue();
    queue.setExecutor(async () => ({}));
    
    const taskId = queue.enqueue("add", { content: "test" });
    
    const start = performance.now();
    const task = queue.getStatus(taskId);
    const duration = performance.now() - start;
    
    expect(duration).toBeLessThan(5);
    expect(task).not.toBeNull();
    
    queue.stop();
  });

  test("批量入队性能", async () => {
    const queue = new TaskQueue();
    queue.setExecutor(async () => ({}));
    
    const start = performance.now();
    
    for (let i = 0; i < 100; i++) {
      queue.enqueue("add", { content: `test-${i}` });
    }
    
    const duration = performance.now() - start;
    
    // 100 个任务入队时间 < 100ms（平均每个 < 1ms）
    expect(duration).toBeLessThan(100);
    expect(queue.getSize()).toBe(100);
    
    queue.stop();
  });

  test("队列大小统计性能", async () => {
    const queue = new TaskQueue({ maxSize: 2000 });
    queue.setExecutor(async () => ({}));
    
    for (let i = 0; i < 1000; i++) {
      queue.enqueue("add", { content: `test-${i}` });
    }
    
    const start = performance.now();
    const size = queue.getSize();
    const duration = performance.now() - start;
    
    expect(duration).toBeLessThan(5);
    expect(size).toBe(1000);
    
    queue.stop();
  });

  test("内存占用合理", async () => {
    const queue = new TaskQueue({ maxSize: 2000 });
    queue.setExecutor(async () => ({}));
    
    const initialMemory = process.memoryUsage().heapUsed;
    
    for (let i = 0; i < 1000; i++) {
      queue.enqueue("add", { content: `test-memory-${i}` });
    }
    
    const afterMemory = process.memoryUsage().heapUsed;
    const memoryIncrease = afterMemory - initialMemory;
    
    // 1000 个任务内存增加 < 5MB
    expect(memoryIncrease).toBeLessThan(5 * 1024 * 1024);
    
    queue.stop();
  });
});
