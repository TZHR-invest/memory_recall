import * as fs from "fs";
import * as path from "path";
import { fileURLToPath } from "url";

export type Locale = "en_US" | "zh_CN";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

export interface LocaleData {
  locale: Locale;
  keywords: string[];
  nudge: string;
  context_header: string;
  user_profile: string;
  recent_context: string;
  project_knowledge: string;
  relevant_memories: string;
  session_summary: string;
  session_summary_sections: {
    user_requests: string;
    final_goal: string;
    work_completed: string;
    remaining_tasks: string;
    active_working_context: string;
    must_not_do: string;
    next_action: string;
  };
  tool_messages: {
    help_title: string;
    mode_add: string;
    mode_search: string;
    mode_profile: string;
    mode_list: string;
    mode_forget: string;
    scope_user: string;
    scope_project: string;
    memory_added: string;
    memory_removed: string;
    cannot_store_private: string;
  };
}

const localeCache: Map<Locale, LocaleData> = new Map();

function loadLocaleFile(locale: Locale): LocaleData {
  const cached = localeCache.get(locale);
  if (cached) return cached;

  const filePath = path.join(__dirname, "i18n", `${locale}.json`);
  try {
    const content = fs.readFileSync(filePath, "utf-8");
    const data = JSON.parse(content) as LocaleData;
    localeCache.set(locale, data);
    return data;
  } catch {
    const fallback = locale === "zh_CN" ? loadLocaleFile("en_US") : getDefaultLocale();
    return fallback;
  }
}

function getDefaultLocale(): LocaleData {
  return {
    locale: "en_US",
    keywords: ["remember", "save this", "don't forget", "important"],
    nudge: "[MEMORY TRIGGER DETECTED]\nThe user wants you to remember something. Use the `memory-recall` tool with `mode: \"add\"` to save this information.",
    context_header: "[MEMORY-RECALL]",
    user_profile: "User Profile",
    recent_context: "Recent Context",
    project_knowledge: "Project Knowledge",
    relevant_memories: "Relevant Memories",
    session_summary: "[Session Summary]",
    session_summary_sections: {
      user_requests: "## 1. User Requests (As-Is)",
      final_goal: "## 2. Final Goal",
      work_completed: "## 3. Work Completed",
      remaining_tasks: "## 4. Remaining Tasks",
      active_working_context: "## 5. Active Working Context (For Seamless Continuation)",
      must_not_do: "## 6. MUST NOT Do (Critical Constraints)",
      next_action: "## 7. Next Action",
    },
    tool_messages: {
      help_title: "Memory Recall Usage Guide",
      mode_add: "Store a new memory",
      mode_search: "Search memories",
      mode_profile: "View user profile",
      mode_list: "List recent memories",
      mode_forget: "Remove a memory",
      scope_user: "Cross-project",
      scope_project: "This project (default)",
      memory_added: "Memory added to {scope} scope",
      memory_removed: "Memory removed",
      cannot_store_private: "Cannot store fully private content",
    },
  };
}

export function getLocale(locale: Locale): LocaleData {
  return loadLocaleFile(locale);
}

export function getAllKeywords(): string[] {
  const enUs = loadLocaleFile("en_US");
  const zhCn = loadLocaleFile("zh_CN");
  return [...new Set([...enUs.keywords, ...zhCn.keywords])];
}

export function detectLocaleFromText(text: string, setting: string = "auto"): Locale {
  if (setting === "zh_CN") return "zh_CN";
  if (setting === "en_US") return "en_US";

  const chineseChars = (text.match(/[\u4e00-\u9fff]/g) || []).length;
  const totalChars = text.replace(/\s/g, "").length;
  return chineseChars / totalChars > 0.3 ? "zh_CN" : "en_US";
}
