import { describe, test, expect, afterAll } from "bun:test";
import { mkdirSync, mkdtempSync, rmSync } from "fs";
import { tmpdir } from "os";
import { join } from "path";
import { spawnSync } from "child_process";
import { getProjectTag } from "../src/config";

const KEY_ID = "085288ba-8eab-439b-b0d4-b92382e0f95d";
const config = { keyId: KEY_ID } as any;

const tmpDirs: string[] = [];
function makeDir(name: string, withGit = false): string {
  const dir = mkdtempSync(join(tmpdir(), "project-tag-test-" + name + "-"));
  tmpDirs.push(dir);
  if (withGit) {
    const res = spawnSync("git", ["init", "-q"], { cwd: dir });
    if (res.status !== 0) {
      throw new Error("git init failed in test");
    }
  }
  return dir;
}

afterAll(() => {
  for (const dir of tmpDirs) {
    rmSync(dir, { recursive: true, force: true });
  }
});

describe("getProjectTag", () => {
  test("普通目录：keyId + 目录名生成", () => {
    const dir = makeDir("repo");
    const tag = getProjectTag(config, dir);
    const base = dir.split("/").pop()!.toLowerCase();
    expect(tag).toBe(KEY_ID + "_project-" + base);
  });

  
  test("隐藏目录（如 ~/.codex）且非 git 仓库：回退 project-default", () => {
    const dir = makeDir("nongit");
    const hidden = join(dir, ".codex");
    mkdirSync(hidden);
    const tag = getProjectTag(config, hidden);
    expect(tag).toBe(KEY_ID + "_project-default");
  });

  test("隐藏目录但处于 git 仓库内：用 git 根目录名", () => {
    const dir = makeDir("gitrepo", true);
    const hidden = join(dir, ".codex");
    mkdirSync(hidden);
    const tag = getProjectTag(config, hidden);
    const rootName = dir.split("/").pop()!.toLowerCase();
    expect(tag).toBe(KEY_ID + "_project-" + rootName);
  });

  test("目录名含空格：转成短横线", () => {
    const dir = makeDir("spaced dir");
    const tag = getProjectTag(config, join(dir, "my project"));
    expect(tag).toBe(KEY_ID + "_project-my-project");
  });

  test("目录名大写：转小写", () => {
    const dir = makeDir("UPPER");
    const tag = getProjectTag(config, join(dir, "MyProject"));
    expect(tag).toBe(KEY_ID + "_project-myproject");
  });

  test("无 keyId：仅项目名", () => {
    const dir = makeDir("nokey");
    const tag = getProjectTag({} as any, dir);
    expect(tag.startsWith("project-")).toBe(true);
  });
});
