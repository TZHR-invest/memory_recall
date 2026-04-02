import { describe, test, expect, beforeEach, afterEach } from "bun:test";
import { TaskQueue, calculateRetryDelay } from "../src/queue";

describe("calculateRetryDelay", () => {
  const policy = {
    maxRetries: 3,
    initialDelay: 1000,
    maxDelay: 10000,
    backoffMultiplier: 2,
  };

  test("第一次重试延迟为 initialDelay", () => {
    expect(calculateRetryDelay(0, policy)).toBe(1000);
  });

  test("第二次重试延迟翻倍", () => {
    expect(calculateRetryDelay(1, policy)).toBe(2000);
  });

  test("第三次重试延迟继续翻倍", () => {
    expect(calculateRetryDelay(2, policy)).toBe(4000);
  });

  test("延迟达到 maxDelay 上限", () => {
    expect(calculateRetryDelay(10, policy)).toBe(10000);
  });
});

describe("TaskQueue", () => {
  let queue: TaskQueue;

  beforeEach(() => {
    queue = new TaskQueue({ maxConcurrency: 2, maxSize: 10 });
  });

  afterEach(() => {
    queue.stop();
  });

  describe("enqueue", () => {
    test("入队成功返回任务 ID", () => {
      const taskId = queue.enqueue("add", { content: "test" });
      expect(taskId).toMatch(/^task_/);
      expect(queue.getSize()).toBe(1);
    });

    test("队列满时拒绝入队", () => {
      const smallQueue = new TaskQueue({ maxSize: 2 });
      smallQueue.enqueue("add", { content: "test1" });
      smallQueue.enqueue("add", { content: "test2" });
      
      expect(() => smallQueue.enqueue("add", { content: "test3" })).toThrow("Queue is full");
      smallQueue.stop();
    });

    test("入队后状态为 pending", () => {
      const taskId = queue.enqueue("add", { content: "test" });
      const task = queue.getStatus(taskId);
      
      expect(task).not.toBeNull();
      expect(task!.status).toBe("pending");
    });
  });

  describe("getStatus", () => {
    test("不存在的任务返回 null", () => {
      expect(queue.getStatus("nonexistent")).toBeNull();
    });

    test("返回完整任务信息", () => {
      const taskId = queue.enqueue("add", { content: "test", containerTag: "user-1" });
      const task = queue.getStatus(taskId);
      
      expect(task).toMatchObject({
        id: taskId,
        type: "add",
        status: "pending",
        retryCount: 0,
      });
      expect(task!.payload.content).toBe("test");
    });
  });

  describe("getAllTasks", () => {
    test("返回所有任务", () => {
      queue.enqueue("add", { content: "test1" });
      queue.enqueue("add", { content: "test2" });
      
      const tasks = queue.getAllTasks();
      expect(tasks.length).toBe(2);
    });

    test("空队列返回空数组", () => {
      expect(queue.getAllTasks().length).toBe(0);
    });
  });

  describe("并发控制", () => {
    test("同时执行的任务不超过 maxConcurrency", async () => {
      const executionOrder: number[] = [];
      const delays = [100, 50, 150];
      
      queue.setExecutor(async (task) => {
        const delay = delays[parseInt(task.payload.content as string)];
        executionOrder.push(Date.now());
        await new Promise(resolve => setTimeout(resolve, delay));
        return {};
      });
      
      queue.start();
      
      queue.enqueue("add", { content: "0" });
      queue.enqueue("add", { content: "1" });
      queue.enqueue("add", { content: "2" });
      
      await new Promise(resolve => setTimeout(resolve, 400));
      
      expect(queue.getRunningCount()).toBeLessThanOrEqual(2);
    });
  });

  describe("重试机制", () => {
    test("成功执行后状态为 success", async () => {
      queue.setExecutor(async () => ({ result: "ok" }));
      queue.start();
      
      const taskId = queue.enqueue("add", { content: "test" });
      
      // 等待任务执行完成
      await new Promise(resolve => setTimeout(resolve, 200));
      
      const task = queue.getStatus(taskId);
      expect(task!.status).toBe("success");
    });

    test("失败任务会被重新入队", async () => {
      const retryQueue = new TaskQueue({ 
        maxConcurrency: 1,
        retryPolicy: { maxRetries: 2, initialDelay: 50, maxDelay: 200, backoffMultiplier: 2 }
      });
      
      let attempts = 0;
      
      retryQueue.setExecutor(async () => {
        attempts++;
        throw new Error("Always fails");
      });
      
      retryQueue.start();
      
      const taskId = retryQueue.enqueue("add", { content: "test" });
      
      // 初始执行: ~100ms, 第一次重试: 100ms + ~100ms, 第二次重试: 200ms + ~100ms
      // 总共需要约 600ms
      await new Promise(resolve => setTimeout(resolve, 800));
      
      const task = retryQueue.getStatus(taskId);
      expect(task!.status).toBe("failed");
      expect(attempts).toBe(3);
      
      retryQueue.stop();
    });

    test("达到最大重试次数后标记为 failed", async () => {
      const retryQueue = new TaskQueue({ 
        maxConcurrency: 1,
        retryPolicy: { maxRetries: 1, initialDelay: 10, maxDelay: 100, backoffMultiplier: 2 }
      });
      
      retryQueue.setExecutor(async () => {
        throw new Error("Always fails");
      });
      
      retryQueue.start();
      
      const taskId = retryQueue.enqueue("add", { content: "test" });
      
      // 等待足够长时间让任务执行和重试
      await new Promise(resolve => setTimeout(resolve, 500));
      
      const task = retryQueue.getStatus(taskId);
      expect(task!.status).toBe("failed");
      expect(task!.retryCount).toBe(1);
      
      retryQueue.stop();
    });

    test("错误历史被记录", async () => {
      const retryQueue = new TaskQueue({ 
        maxConcurrency: 1,
        retryPolicy: { maxRetries: 2, initialDelay: 10, maxDelay: 100, backoffMultiplier: 2 }
      });
      
      retryQueue.setExecutor(async () => {
        throw new Error("Test error");
      });
      
      retryQueue.start();
      
      const taskId = retryQueue.enqueue("add", { content: "test" });
      
      // 等待足够长时间让任务执行和重试
      await new Promise(resolve => setTimeout(resolve, 800));
      
      const task = retryQueue.getStatus(taskId);
      expect(task!.errorHistory).toBeDefined();
      expect(task!.errorHistory!.length).toBeGreaterThan(0);
      
      retryQueue.stop();
    });
  });

  describe("手动重试", () => {
    test("只能重试失败的任务", () => {
      const taskId = queue.enqueue("add", { content: "test" });
      
      expect(queue.retry(taskId)).toBe(false);
    });

    test("重试成功返回 true", async () => {
      const retryQueue = new TaskQueue({ 
        maxConcurrency: 1,
        retryPolicy: { maxRetries: 1, initialDelay: 10, maxDelay: 100, backoffMultiplier: 2 }
      });
      
      retryQueue.setExecutor(async () => {
        throw new Error("Always fails");
      });
      
      retryQueue.start();
      
      const taskId = retryQueue.enqueue("add", { content: "test" });
      
      // 等待足够长时间让任务执行和失败
      await new Promise(resolve => setTimeout(resolve, 300));
      
      const task = retryQueue.getStatus(taskId);
      expect(task!.status).toBe("failed");
      
      expect(retryQueue.retry(taskId)).toBe(true);
      
      const retriedTask = retryQueue.getStatus(taskId);
      expect(retriedTask!.status).toBe("pending");
      expect(retriedTask!.retryCount).toBe(0);
      
      retryQueue.stop();
    });
  });

  describe("clearCompleted", () => {
    test("清理成功和失败的任务", async () => {
      queue.setExecutor(async () => ({}));
      queue.start();
      
      const task1 = queue.enqueue("add", { content: "test1" });
      const task2 = queue.enqueue("add", { content: "test2" });
      
      // 等待足够长时间让任务执行完成
      await new Promise(resolve => setTimeout(resolve, 300));
      
      const cleared = queue.clearCompleted();
      expect(cleared).toBe(2);
      expect(queue.getSize()).toBe(0);
    });
  });

  describe("统计方法", () => {
    test("getPendingCount 正确", () => {
      queue.enqueue("add", { content: "test1" });
      queue.enqueue("add", { content: "test2" });
      
      expect(queue.getPendingCount()).toBe(2);
    });

    test("getRunningCount 正确", async () => {
      queue.setExecutor(async () => {
        await new Promise(resolve => setTimeout(resolve, 100));
        return {};
      });
      queue.start();
      
      queue.enqueue("add", { content: "test1" });
      queue.enqueue("add", { content: "test2" });
      
      await new Promise(resolve => setTimeout(resolve, 10));
      
      expect(queue.getRunningCount()).toBeLessThanOrEqual(2);
    });

    test("getSize 正确", () => {
      expect(queue.getSize()).toBe(0);
      
      queue.enqueue("add", { content: "test" });
      expect(queue.getSize()).toBe(1);
    });
  });
});
