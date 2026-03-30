import { describe, test, expect } from "bun:test";
import {
  traverseFromSeeds,
  calculateRelationScore,
  extractEntitiesFromQuery,
  findBySharedEntities,
  mergeAndDedupe,
  RELATION_WEIGHTS,
  ENTITY_WEIGHTS,
} from "../src/context";
import type { GraphNode, GraphEdge, SearchResult } from "../src/client";

describe("Graph Traversal", () => {
  test("traverseFromSeeds returns empty for empty seeds", () => {
    const result = traverseFromSeeds([], [], [], 2, 5);
    expect(result).toEqual([]);
  });

  test("traverseFromSeeds traverses updates relation", () => {
    const seeds: SearchResult[] = [
      { id: "mem_a", content: "Memory A", similarity: 0.9 },
    ];
    const nodes: GraphNode[] = [
      { id: "mem_a", type: "memory", content: "Memory A", is_static: false, is_latest: true, is_inference: false },
      { id: "mem_b", type: "memory", content: "Memory B", is_static: false, is_latest: false, is_inference: false },
    ];
    const edges: GraphEdge[] = [
      { source: "mem_a", target: "mem_b", type: "updates", confidence: 0.9 },
    ];
    
    const result = traverseFromSeeds(seeds, edges, nodes, 2, 5);
    
    expect(result.length).toBe(1);
    expect(result[0].id).toBe("mem_b");
    expect(result[0].relationType).toBe("updates");
  });

  test("traverseFromSeeds respects maxDepth", () => {
    const seeds: SearchResult[] = [
      { id: "mem_a", content: "Memory A", similarity: 0.9 },
    ];
    const nodes: GraphNode[] = [
      { id: "mem_a", type: "memory", content: "A", is_static: false, is_latest: true, is_inference: false },
      { id: "mem_b", type: "memory", content: "B", is_static: false, is_latest: true, is_inference: false },
      { id: "mem_c", type: "memory", content: "C", is_static: false, is_latest: true, is_inference: false },
    ];
    const edges: GraphEdge[] = [
      { source: "mem_a", target: "mem_b", type: "updates", confidence: 0.9 },
      { source: "mem_b", target: "mem_c", type: "updates", confidence: 0.9 },
    ];
    
    const result = traverseFromSeeds(seeds, edges, nodes, 1, 5);
    
    expect(result.length).toBe(1);
    expect(result[0].id).toBe("mem_b");
  });

  test("traverseFromSeeds respects maxNodes", () => {
    const seeds: SearchResult[] = [
      { id: "mem_a", content: "Memory A", similarity: 0.9 },
    ];
    const nodes: GraphNode[] = [
      { id: "mem_a", type: "memory", content: "A", is_static: false, is_latest: true, is_inference: false },
      { id: "mem_b", type: "memory", content: "B", is_static: false, is_latest: true, is_inference: false },
      { id: "mem_c", type: "memory", content: "C", is_static: false, is_latest: true, is_inference: false },
    ];
    const edges: GraphEdge[] = [
      { source: "mem_a", target: "mem_b", type: "extends", confidence: 0.9 },
      { source: "mem_a", target: "mem_c", type: "extends", confidence: 0.8 },
    ];
    
    const result = traverseFromSeeds(seeds, edges, nodes, 2, 1);
    
    expect(result.length).toBe(1);
  });
});

describe("Relation Score Calculation", () => {
  test("updates has highest weight", () => {
    const edge: GraphEdge = { source: "a", target: "b", type: "updates", confidence: 0.9 };
    expect(calculateRelationScore(edge)).toBe(0.9 * RELATION_WEIGHTS["updates"]);
  });

  test("extends has medium weight", () => {
    const edge: GraphEdge = { source: "a", target: "b", type: "extends", confidence: 0.9 };
    expect(calculateRelationScore(edge)).toBe(0.9 * RELATION_WEIGHTS["extends"]);
  });

  test("derives has lowest weight", () => {
    const edge: GraphEdge = { source: "a", target: "b", type: "derives", confidence: 0.9 };
    expect(calculateRelationScore(edge)).toBe(0.9 * RELATION_WEIGHTS["derives"]);
  });
});

describe("Entity Extraction", () => {
  test("extracts person from Chinese pattern", () => {
    const result = extractEntitiesFromQuery("和Alice见面");
    expect(result.some(e => e.type === "person")).toBe(true);
  });

  test("extracts organization from Chinese pattern", () => {
    const result = extractEntitiesFromQuery("在字节跳动工作");
    expect(result.some(e => e.type === "organization")).toBe(true);
  });

  test("extracts location from Chinese pattern", () => {
    const result = extractEntitiesFromQuery("住在北京");
    expect(result.some(e => e.type === "location")).toBe(true);
  });

  test("returns empty for no entities", () => {
    const result = extractEntitiesFromQuery("今天天气很好");
    expect(result).toEqual([]);
  });
});

describe("Entity-based Recall", () => {
  test("findBySharedEntities returns matching nodes", () => {
    const nodes: GraphNode[] = [
      { 
        id: "mem_a", 
        type: "memory", 
        content: "Memory about Alice", 
        is_static: false, 
        is_latest: true, 
        is_inference: false,
        entities: { person: ["Alice"] }
      },
      { 
        id: "mem_b", 
        type: "memory", 
        content: "Memory about Bob", 
        is_static: false, 
        is_latest: true, 
        is_inference: false,
        entities: { person: ["Bob"] }
      },
    ];
    const queryEntities = [{ type: "person", values: ["Alice"] }];
    
    const result = findBySharedEntities(nodes, queryEntities, 5);
    
    expect(result.length).toBe(1);
    expect(result[0].id).toBe("mem_a");
  });

  test("findBySharedEntities respects maxNodes", () => {
    const nodes: GraphNode[] = [
      { id: "mem_a", type: "memory", content: "A", is_static: false, is_latest: true, is_inference: false, entities: { person: ["Alice"] } },
      { id: "mem_b", type: "memory", content: "B", is_static: false, is_latest: true, is_inference: false, entities: { person: ["Alice"] } },
      { id: "mem_c", type: "memory", content: "C", is_static: false, is_latest: true, is_inference: false, entities: { person: ["Alice"] } },
    ];
    const queryEntities = [{ type: "person", values: ["Alice"] }];
    
    const result = findBySharedEntities(nodes, queryEntities, 2);
    
    expect(result.length).toBe(2);
  });

  test("findBySharedEntities returns empty for no matches", () => {
    const nodes: GraphNode[] = [
      { id: "mem_a", type: "memory", content: "A", is_static: false, is_latest: true, is_inference: false, entities: { person: ["Bob"] } },
    ];
    const queryEntities = [{ type: "person", values: ["Alice"] }];
    
    const result = findBySharedEntities(nodes, queryEntities, 5);
    
    expect(result).toEqual([]);
  });
});

describe("Merge and Dedupe", () => {
  test("merges results from multiple sources", () => {
    const vector: SearchResult[] = [
      { id: "mem_a", content: "A", similarity: 0.9 },
    ];
    const relation = [
      { id: "mem_b", content: "B", similarity: 0.8, source: "relation" as const, depth: 1, relationType: "updates" as const },
    ];
    const entity = [
      { id: "mem_c", content: "C", similarity: 0.7, source: "entity" as const, depth: 0, matchedEntities: { person: ["Alice"] } },
    ];
    
    const result = mergeAndDedupe(vector, relation, entity);
    
    expect(result.length).toBe(3);
  });

  test("deduplicates by id", () => {
    const vector: SearchResult[] = [
      { id: "mem_a", content: "A", similarity: 0.9 },
    ];
    const relation = [
      { id: "mem_a", content: "A", similarity: 0.8, source: "relation" as const, depth: 1, relationType: "updates" as const },
    ];
    const entity: never[] = [];
    
    const result = mergeAndDedupe(vector, relation, entity);
    
    expect(result.length).toBe(1);
    expect(result[0].source).toBe("vector");
  });

  test("sorts by similarity descending", () => {
    const vector: SearchResult[] = [
      { id: "mem_a", content: "A", similarity: 0.5 },
    ];
    const relation = [
      { id: "mem_b", content: "B", similarity: 0.9, source: "relation" as const, depth: 1, relationType: "updates" as const },
    ];
    const entity: never[] = [];
    
    const result = mergeAndDedupe(vector, relation, entity);
    
    expect(result[0].id).toBe("mem_b");
    expect(result[1].id).toBe("mem_a");
  });
});
