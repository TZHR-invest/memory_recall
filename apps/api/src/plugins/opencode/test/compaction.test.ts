import { describe, test, expect, mock } from "bun:test";
import { CompactionHook } from "../src/compaction";

function makeLogger() {
  return {
    info: mock(() => {}),
    warn: mock(() => {}),
    error: mock(() => {}),
    debug: mock(() => {}),
  };
}

describe("CompactionHook.injectCompactionContext", () => {
  test("appends AI guidance and project memories to context", async () => {
    const apiClient = {
      listMemories: mock(async () => [
        { id: "m1", content: "项目使用 FastAPI", is_static: false },
        { id: "m2", content: "[会话摘要] should be filtered", is_static: false },
        { id: "m3", content: "用户偏好中文", is_static: false },
      ]),
    };
    const config = {
      maxProjectMemories: 5,
      language: "zh_CN",
    };
    const logger = makeLogger();
    const hook = new CompactionHook(apiClient as any, config as any, { user: "u", project: "p" }, logger as any);

    const context: string[] = [];
    await hook.injectCompactionContext("s1", context, ["guidance line"]);

    expect(context.length).toBe(2);
    expect(context[0]).toBe("guidance line");
    expect(context[1]).toContain("## 持久记忆");
    expect(context[1]).toContain("- 项目使用 FastAPI");
    expect(context[1]).not.toContain("会话摘要");
  });

  test("fail-open: listMemories error does not throw and still injects guidance", async () => {
    const apiClient = {
      listMemories: mock(async () => {
        throw new Error("db down");
      }),
    };
    const logger = makeLogger();
    const hook = new CompactionHook(
      apiClient as any,
      { maxProjectMemories: 5, language: "zh_CN" } as any,
      { user: "u", project: "p" },
      logger as any
    );

    const context: string[] = [];
    await hook.injectCompactionContext("s1", context, ["guidance line"]);

    expect(context.length).toBe(1);
    expect(context[0]).toBe("guidance line");
  });

  test("no guidance and no memories leaves context untouched", async () => {
    const apiClient = { listMemories: mock(async () => []) };
    const logger = makeLogger();
    const hook = new CompactionHook(
      apiClient as any,
      { maxProjectMemories: 5, language: "en_US" } as any,
      { user: "u", project: "p" },
      logger as any
    );

    const context: string[] = [];
    await hook.injectCompactionContext("s1", context, []);
    expect(context.length).toBe(0);
  });

  test("uses English heading for en_US", async () => {
    const apiClient = {
      listMemories: mock(async () => [{ id: "m1", content: "Project uses FastAPI", is_static: false }]),
    };
    const logger = makeLogger();
    const hook = new CompactionHook(
      apiClient as any,
      { maxProjectMemories: 5, language: "en_US" } as any,
      { user: "u", project: "p" },
      logger as any
    );

    const context: string[] = [];
    await hook.injectCompactionContext("s1", context, []);
    expect(context[0]).toContain("## Persistent Memory");
  });
});
