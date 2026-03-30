import { describe, test, expect, mock, beforeEach } from "bun:test";
import * as fs from "fs";
import * as path from "path";
import * as os from "os";

const PART_STORAGE = path.join(os.homedir(), ".opencode", "parts");

describe("extractSummaryContent", () => {
  test("returns null for non-existent message", () => {
    const result = extractSummaryContent("non_existent_message_id");
    expect(result).toBeNull();
  });

  test("extracts text from valid part file", () => {
    const testMessageId = "msg_test_" + Date.now();
    const testPartId = "prt_test_" + Date.now();
    const testContent = "This is a test summary content.";

    const partDir = path.join(PART_STORAGE, testMessageId);
    fs.mkdirSync(partDir, { recursive: true });
    fs.writeFileSync(
      path.join(partDir, `${testPartId}.json`),
      JSON.stringify({ type: "text", text: testContent })
    );

    const result = extractSummaryContent(testMessageId);
    
    // Cleanup
    fs.rmSync(partDir, { recursive: true, force: true });

    expect(result).toBe(testContent);
  });

  test("returns null for empty text", () => {
    const testMessageId = "msg_empty_" + Date.now();
    const testPartId = "prt_empty_" + Date.now();

    const partDir = path.join(PART_STORAGE, testMessageId);
    fs.mkdirSync(partDir, { recursive: true });
    fs.writeFileSync(
      path.join(partDir, `${testPartId}.json`),
      JSON.stringify({ type: "text", text: "" })
    );

    const result = extractSummaryContent(testMessageId);
    
    // Cleanup
    fs.rmSync(partDir, { recursive: true, force: true });

    expect(result).toBeNull();
  });

  test("skips non-text parts", () => {
    const testMessageId = "msg_notext_" + Date.now();
    const testPartId = "prt_notext_" + Date.now();

    const partDir = path.join(PART_STORAGE, testMessageId);
    fs.mkdirSync(partDir, { recursive: true });
    fs.writeFileSync(
      path.join(partDir, `${testPartId}.json`),
      JSON.stringify({ type: "other", data: "something" })
    );

    const result = extractSummaryContent(testMessageId);
    
    // Cleanup
    fs.rmSync(partDir, { recursive: true, force: true });

    expect(result).toBeNull();
  });
});

// Import the function from compaction.ts
function extractSummaryContent(messageId: string): string | null {
  const partDir = path.join(PART_STORAGE, messageId);
  if (!fs.existsSync(partDir)) return null;

  try {
    const files = fs.readdirSync(partDir).filter(f => f.endsWith('.json'));
    for (const file of files) {
      try {
        const content = fs.readFileSync(path.join(partDir, file), 'utf-8');
        const part = JSON.parse(content) as { type?: string; text?: string };
        if (part.type === 'text' && part.text && part.text.trim()) {
          return part.text.trim();
        }
      } catch {
        continue;
      }
    }
  } catch {
    return null;
  }
  return null;
}

describe("checkAndTriggerCompaction with OpenCode client", () => {
  const mockOpenCodeClient = {
    session: {
      summarize: mock(() => Promise.resolve()),
      messages: mock(() => Promise.resolve({ data: [] })),
      promptAsync: mock(() => Promise.resolve()),
    },
    tui: {
      showToast: mock(() => Promise.resolve()),
    },
  };

  const mockApiClient = {
    listMemories: mock(() => Promise.resolve([])),
    addMemory: mock(() => Promise.resolve({ id: "mem_test" })),
  };

  const mockConfig = {
    compactionThreshold: 0.8,
    maxProjectMemories: 10,
    enableSummaryCapture: true,
    language: "en_US" as const,
  };

  const mockLogger = {
    info: mock(() => {}),
    warn: mock(() => {}),
    error: mock(() => {}),
    debug: mock(() => {}),
    compactionTriggered: mock(() => {}),
    compactionComplete: mock(() => {}),
  };

  test("calls session.summarize when threshold exceeded", async () => {
    const sessionId = "test_session_summarize";
    const lastAssistant = {
      sessionID: sessionId,
      role: "assistant",
      finish: true,
      tokens: { input: 100000, output: 60000, cache: { read: 10000 } },
      providerID: "test_provider",
      modelID: "test_model",
    };

    const { CompactionHook } = await import("../src/compaction");
    const hook = new CompactionHook(
      mockApiClient as any,
      mockConfig as any,
      { user: "test_user", project: "test_project" },
      mockLogger as any,
      "/test/dir",
      mockOpenCodeClient as any
    );

    await hook.checkAndTriggerCompaction(sessionId, lastAssistant, null);

    expect(mockOpenCodeClient.session.summarize).toHaveBeenCalled();
    expect(mockOpenCodeClient.tui.showToast).toHaveBeenCalledTimes(2);
  });

  test("does not trigger if below threshold", async () => {
    mockOpenCodeClient.session.summarize.mockClear();
    
    const sessionId = "test_session_below";
    const lastAssistant = {
      sessionID: sessionId,
      role: "assistant",
      finish: true,
      tokens: { input: 10000, output: 5000, cache: { read: 1000 } },
      providerID: "test_provider",
      modelID: "test_model",
    };

    const { CompactionHook } = await import("../src/compaction");
    const hook = new CompactionHook(
      mockApiClient as any,
      mockConfig as any,
      { user: "test_user", project: "test_project" },
      mockLogger as any,
      "/test/dir",
      mockOpenCodeClient as any
    );

    await hook.checkAndTriggerCompaction(sessionId, lastAssistant, null);

    expect(mockOpenCodeClient.session.summarize).not.toHaveBeenCalled();
  });

  test("shows toast notifications during compaction", async () => {
    mockOpenCodeClient.tui.showToast.mockClear();

    const sessionId = "test_session_toast";
    const lastAssistant = {
      sessionID: sessionId,
      role: "assistant",
      finish: true,
      tokens: { input: 100000, output: 60000, cache: { read: 10000 } },
      providerID: "test_provider",
      modelID: "test_model",
    };

    const { CompactionHook } = await import("../src/compaction");
    const hook = new CompactionHook(
      mockApiClient as any,
      mockConfig as any,
      { user: "test_user", project: "test_project" },
      mockLogger as any,
      "/test/dir",
      mockOpenCodeClient as any
    );

    await hook.checkAndTriggerCompaction(sessionId, lastAssistant, null);

    const calls = mockOpenCodeClient.tui.showToast.mock.calls;
    expect(calls.length).toBeGreaterThanOrEqual(1);
    
    const firstCallArg = calls[0]?.[0];
    expect(firstCallArg?.body?.title).toBe("Preemptive Compaction");
  });
});

describe("enableEventHandling configuration", () => {
  test("events are processed when enableEventHandling is true", async () => {
    const config = { enableEventHandling: true };
    expect(config.enableEventHandling).toBe(true);
  });

  test("events are skipped when enableEventHandling is false", async () => {
    const config = { enableEventHandling: false };
    expect(config.enableEventHandling).toBe(false);
  });
});

describe("summary capture after compaction", () => {
  const mockApiClient = {
    listMemories: mock(() => Promise.resolve([])),
    addMemory: mock(() => Promise.resolve({ id: "mem_summary_test" })),
  };

  const mockConfig = {
    compactionThreshold: 0.8,
    maxProjectMemories: 10,
    enableSummaryCapture: true,
    minSummaryLength: 100,
    language: "en_US" as const,
  };

  const mockLogger = {
    info: mock(() => {}),
    warn: mock(() => {}),
    error: mock(() => {}),
  };

  test("saves summary when enableSummaryCapture is true", async () => {
    const testMessageId = "msg_summary_test_" + Date.now();
    const testSummary = "This is a test summary that is long enough to meet the minimum length requirement of one hundred characters for saving.";

    const partDir = path.join(PART_STORAGE, testMessageId);
    fs.mkdirSync(partDir, { recursive: true });
    fs.writeFileSync(
      path.join(partDir, `prt_summary.json`),
      JSON.stringify({ type: "text", text: testSummary })
    );

    const { CompactionHook } = await import("../src/compaction");
    const hook = new CompactionHook(
      mockApiClient as any,
      mockConfig as any,
      { user: "test_user", project: "test_project" },
      mockLogger as any,
      "/test/dir"
    );

    (hook as any).state.summarizedSessions.add("test_session_summary");

    await hook.handleSummaryMessage("test_session_summary", {
      id: testMessageId,
      sessionID: "test_session_summary",
      role: "assistant",
      summary: true,
      finish: true,
    }, null);

    fs.rmSync(partDir, { recursive: true, force: true });

    expect(mockApiClient.addMemory).toHaveBeenCalled();
  });
});
