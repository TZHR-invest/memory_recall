import { describe, test, expect } from "bun:test";
import { computeContentHash, deduplicateAcrossScopes } from "../src/context";
import type { Profile, Memory, SearchResult, ChunkSearchResult } from "../src/client";

describe("computeContentHash", () => {
  test("returns consistent hash for same content", () => {
    const content = "Test content for hashing";
    const hash1 = computeContentHash(content);
    const hash2 = computeContentHash(content);
    expect(hash1).toBe(hash2);
  });

  test("returns different hash for different content", () => {
    const hash1 = computeContentHash("Content A");
    const hash2 = computeContentHash("Content B");
    expect(hash1).not.toBe(hash2);
  });

  test("handles empty string", () => {
    const hash = computeContentHash("");
    expect(hash).toBeDefined();
    expect(hash.length).toBe(16);
  });

  test("handles unicode content", () => {
    const hash = computeContentHash("中文内容测试 🎉");
    expect(hash).toBeDefined();
    expect(hash.length).toBe(16);
  });
});

describe("deduplicateAcrossScopes", () => {
  const createMemory = (id: string, content: string): Memory => ({
    id,
    content,
    container_tag: "test",
    is_static: true,
    is_latest: true,
    created_at: new Date().toISOString(),
  });

  test("removes project memories that match user static facts", () => {
    const duplicateContent = "This is a duplicate content";
    
    const profile: Profile = {
      static: [duplicateContent],
      dynamic: [],
    };
    
    const projectMemories: Memory[] = [
      createMemory("mem_1", duplicateContent),
      createMemory("mem_2", "Unique project memory"),
    ];
    
    const result = deduplicateAcrossScopes(profile, projectMemories);
    
    expect(result.staticFacts).toHaveLength(1);
    expect(result.dedupedProjectMemories).toHaveLength(1);
    expect(result.dedupedProjectMemories[0].content).toBe("Unique project memory");
    expect(result.dedupStats.projectMemoriesFiltered).toBe(1);
  });

  test("removes project memories that match user dynamic facts", () => {
    const duplicateContent = "Dynamic activity duplicate";
    
    const profile: Profile = {
      static: [],
      dynamic: [duplicateContent],
    };
    
    const projectMemories: Memory[] = [
      createMemory("mem_1", duplicateContent),
      createMemory("mem_2", "Unique project memory"),
    ];
    
    const result = deduplicateAcrossScopes(profile, projectMemories);
    
    expect(result.dedupedProjectMemories).toHaveLength(1);
    expect(result.dedupStats.projectMemoriesFiltered).toBe(1);
  });

  test("keeps all project memories when no duplicates", () => {
    const profile: Profile = {
      static: ["User fact 1", "User fact 2"],
      dynamic: ["User activity"],
    };
    
    const projectMemories: Memory[] = [
      createMemory("mem_1", "Project memory 1"),
      createMemory("mem_2", "Project memory 2"),
      createMemory("mem_3", "Project memory 3"),
    ];
    
    const result = deduplicateAcrossScopes(profile, projectMemories);
    
    expect(result.dedupedProjectMemories).toHaveLength(3);
    expect(result.dedupStats.projectMemoriesFiltered).toBe(0);
  });

  test("handles null profile", () => {
    const projectMemories: Memory[] = [
      createMemory("mem_1", "Project memory 1"),
    ];
    
    const result = deduplicateAcrossScopes(null, projectMemories);
    
    expect(result.staticFacts).toHaveLength(0);
    expect(result.dynamicFacts).toHaveLength(0);
    expect(result.dedupedProjectMemories).toHaveLength(1);
  });

  test("handles empty project memories", () => {
    const profile: Profile = {
      static: ["User fact"],
      dynamic: [],
    };
    
    const result = deduplicateAcrossScopes(profile, []);
    
    expect(result.dedupedProjectMemories).toHaveLength(0);
    expect(result.dedupStats.projectMemoriesFiltered).toBe(0);
  });

  test("user priority: keeps user content, removes duplicate project content", () => {
    const sharedContent = "Shared between user and project";
    
    const profile: Profile = {
      static: [sharedContent],
      dynamic: [],
    };
    
    const projectMemories: Memory[] = [
      createMemory("mem_proj", sharedContent),
    ];
    
    const result = deduplicateAcrossScopes(profile, projectMemories);
    
    expect(result.staticFacts).toContain(sharedContent);
    expect(result.dedupedProjectMemories).toHaveLength(0);
  });

  test("removes multiple duplicates from project memories", () => {
    const duplicate1 = "Duplicate content 1";
    const duplicate2 = "Duplicate content 2";
    
    const profile: Profile = {
      static: [duplicate1],
      dynamic: [duplicate2],
    };
    
    const projectMemories: Memory[] = [
      createMemory("mem_1", duplicate1),
      createMemory("mem_2", duplicate2),
      createMemory("mem_3", "Unique content"),
    ];
    
    const result = deduplicateAcrossScopes(profile, projectMemories);
    
    expect(result.dedupedProjectMemories).toHaveLength(1);
    expect(result.dedupStats.projectMemoriesFiltered).toBe(2);
  });

  test("removes userMemories that match profile", () => {
    const duplicateContent = "User profile fact";
    
    const profile: Profile = {
      static: [duplicateContent],
      dynamic: [],
    };

    const userMemories: SearchResult[] = [
      { id: "um_1", content: duplicateContent, similarity: 0.9 },
      { id: "um_2", content: "Unique user memory", similarity: 0.8 },
    ];
    
    const result = deduplicateAcrossScopes(profile, [], userMemories, []);
    
    expect(result.dedupedUserMemories).toHaveLength(1);
    expect(result.dedupedUserMemories[0].content).toBe("Unique user memory");
    expect(result.dedupStats.userMemoriesFiltered).toBe(1);
  });

  test("removes userMemories that match projectMemories", () => {
    const duplicateContent = "Shared project memory";
    
    const projectMemories: Memory[] = [
      createMemory("pm_1", duplicateContent),
    ];

    const userMemories: SearchResult[] = [
      { id: "um_1", content: duplicateContent, similarity: 0.9 },
      { id: "um_2", content: "Unique user memory", similarity: 0.8 },
    ];
    
    const result = deduplicateAcrossScopes(null, projectMemories, userMemories, []);
    
    expect(result.dedupedUserMemories).toHaveLength(1);
    expect(result.dedupStats.userMemoriesFiltered).toBe(1);
  });

  test("removes chunks that match profile or memories", () => {
    const profileContent = "Profile fact";
    const memoryContent = "Memory content";
    
    const profile: Profile = {
      static: [profileContent],
      dynamic: [],
    };

    const projectMemories: Memory[] = [
      createMemory("pm_1", memoryContent),
    ];

    const chunks: ChunkSearchResult[] = [
      { id: "ch_1", content: profileContent, document_id: "doc_1", similarity: 0.9 },
      { id: "ch_2", content: memoryContent, document_id: "doc_1", similarity: 0.85 },
      { id: "ch_3", content: "Unique chunk content", document_id: "doc_2", similarity: 0.8 },
    ];
    
    const result = deduplicateAcrossScopes(profile, projectMemories, [], chunks);
    
    expect(result.dedupedChunks).toHaveLength(1);
    expect(result.dedupedChunks[0].content).toBe("Unique chunk content");
    expect(result.dedupStats.chunksFiltered).toBe(2);
  });

  test("full deduplication chain: profile > projectMemory > userMemory > chunk", () => {
    const profileContent = "Profile content";
    const projectContent = "Project content";
    const userContent = "User content";
    
    const profile: Profile = {
      static: [profileContent],
      dynamic: [],
    };

    const projectMemories: Memory[] = [
      createMemory("pm_1", projectContent),
    ];

    const userMemories: SearchResult[] = [
      { id: "um_1", content: userContent, similarity: 0.9 },
    ];

    const chunks: ChunkSearchResult[] = [
      { id: "ch_1", content: profileContent, document_id: "doc_1", similarity: 0.9 },
      { id: "ch_2", content: projectContent, document_id: "doc_1", similarity: 0.9 },
      { id: "ch_3", content: userContent, document_id: "doc_2", similarity: 0.9 },
      { id: "ch_4", content: "Unique chunk", document_id: "doc_3", similarity: 0.9 },
    ];
    
    const result = deduplicateAcrossScopes(profile, projectMemories, userMemories, chunks);
    
    expect(result.staticFacts).toContain(profileContent);
    expect(result.dedupedProjectMemories).toHaveLength(1);
    expect(result.dedupedUserMemories).toHaveLength(1);
    expect(result.dedupedChunks).toHaveLength(1);
    expect(result.dedupedChunks[0].content).toBe("Unique chunk");
  });
});
