import type { AICreateCachedSteps, AICreateStepKey } from "@/types/novel";

export interface AICreateCacheInput {
  user_idea: string;
  number_of_chapters: number;
  words_per_chapter: number;
}

export interface AICreateCacheRecord {
  input: AICreateCacheInput;
  steps: AICreateCachedSteps;
  failed_step?: AICreateStepKey;
  updated_at: string;
}

const AI_CREATE_CACHE_KEY = "ai_create_novel_cache";
const STEP_ORDER: AICreateStepKey[] = ["expand_idea", "extract_idea", "core_seed", "novel_meta"];

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isString(value: unknown): value is string {
  return typeof value === "string" && value.trim().length > 0;
}

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item) => typeof item === "string");
}

function normalizeInput(value: unknown): AICreateCacheInput | null {
  if (!isObject(value)) {
    return null;
  }

  const userIdea = value.user_idea;
  const chapters = value.number_of_chapters;
  const wordsPerChapter = value.words_per_chapter;
  if (!isString(userIdea) || typeof chapters !== "number" || typeof wordsPerChapter !== "number") {
    return null;
  }

  return {
    user_idea: userIdea,
    number_of_chapters: chapters,
    words_per_chapter: wordsPerChapter,
  };
}

function normalizeSteps(value: unknown): AICreateCachedSteps {
  if (!isObject(value)) {
    return {};
  }

  const steps: AICreateCachedSteps = {};
  const expandIdea = value.expand_idea;
  if (isObject(expandIdea) && isString(expandIdea.plot)) {
    steps.expand_idea = { plot: expandIdea.plot };
  }

  const extractIdea = value.extract_idea;
  if (
    isObject(extractIdea) &&
    isString(extractIdea.genre) &&
    isString(extractIdea.tone) &&
    isString(extractIdea.target_audience) &&
    isString(extractIdea.core_idea)
  ) {
    steps.extract_idea = {
      ...(isString(extractIdea.plot) && { plot: extractIdea.plot }),
      genre: extractIdea.genre,
      tone: extractIdea.tone,
      target_audience: extractIdea.target_audience,
      core_idea: extractIdea.core_idea,
    };
  }

  const coreSeed = value.core_seed;
  if (isObject(coreSeed) && isString(coreSeed.core_seed)) {
    steps.core_seed = { core_seed: coreSeed.core_seed };
  }

  const novelMeta = value.novel_meta;
  if (
    isObject(novelMeta) &&
    isString(novelMeta.title) &&
    isString(novelMeta.subtitle) &&
    isString(novelMeta.introduction) &&
    isString(novelMeta.summary) &&
    isString(novelMeta.worldview) &&
    isString(novelMeta.writing_style) &&
    isString(novelMeta.narrative_pov) &&
    isString(novelMeta.era_background) &&
    isStringArray(novelMeta.tags)
  ) {
    steps.novel_meta = {
      title: novelMeta.title,
      subtitle: novelMeta.subtitle,
      introduction: novelMeta.introduction,
      summary: novelMeta.summary,
      worldview: novelMeta.worldview,
      writing_style: novelMeta.writing_style,
      narrative_pov: novelMeta.narrative_pov,
      era_background: novelMeta.era_background,
      tags: novelMeta.tags,
    };
  }

  return trimCachedStepsToPrefix(steps);
}

/**
 * 读取浏览器本地保存的 AI 创建小说流程缓存。
 *
 * Args:
 *   None.
 *
 * Returns:
 *   校验通过的缓存记录；不存在或结构非法时返回 null。
 */
export function loadAICreateCache(): AICreateCacheRecord | null {
  if (typeof window === "undefined") {
    return null;
  }

  try {
    const raw = window.localStorage.getItem(AI_CREATE_CACHE_KEY);
    if (!raw) {
      return null;
    }

    const parsed = JSON.parse(raw);
    if (!isObject(parsed)) {
      return null;
    }

    const input = normalizeInput(parsed.input);
    if (!input) {
      return null;
    }

    const steps = normalizeSteps(parsed.steps);
    const failedStep = STEP_ORDER.includes(parsed.failed_step as AICreateStepKey)
      ? (parsed.failed_step as AICreateStepKey)
      : undefined;
    return {
      input,
      steps,
      failed_step: failedStep,
      updated_at: isString(parsed.updated_at) ? parsed.updated_at : new Date().toISOString(),
    };
  } catch {
    return null;
  }
}

/**
 * 保存 AI 创建小说流程缓存到浏览器本地存储。
 *
 * Args:
 *   input: 当前流程绑定的核心输入。
 *   steps: 已完成步骤结果。
 *   failedStep: 最近失败的步骤，可为空。
 *
 * Returns:
 *   无返回值。
 */
export function saveAICreateCache(
  input: AICreateCacheInput,
  steps: AICreateCachedSteps,
  failedStep?: AICreateStepKey,
): void {
  if (typeof window === "undefined") {
    return;
  }

  const record: AICreateCacheRecord = {
    input,
    steps: trimCachedStepsToPrefix(steps),
    failed_step: failedStep,
    updated_at: new Date().toISOString(),
  };

  try {
    window.localStorage.setItem(AI_CREATE_CACHE_KEY, JSON.stringify(record));
  } catch {
    // 本地存储不可用时不中断生成流程，当前页面内状态仍可继续重试。
  }
}

/**
 * 清理 AI 创建小说流程缓存。
 *
 * Args:
 *   None.
 *
 * Returns:
 *   无返回值。
 */
export function clearAICreateCache(): void {
  if (typeof window === "undefined") {
    return;
  }

  try {
    window.localStorage.removeItem(AI_CREATE_CACHE_KEY);
  } catch {
    // 清理失败不影响后续页面跳转或再次创建。
  }
}

/**
 * 判断缓存是否属于当前核心输入。
 *
 * Args:
 *   record: 本地缓存记录。
 *   input: 当前页面输入。
 *
 * Returns:
 *   核心输入完全一致时返回 true。
 */
export function isSameAICreateInput(record: AICreateCacheRecord | null, input: AICreateCacheInput): boolean {
  return (
    record?.input.user_idea === input.user_idea &&
    record.input.number_of_chapters === input.number_of_chapters &&
    record.input.words_per_chapter === input.words_per_chapter
  );
}

/**
 * 只保留从第一步开始连续存在的缓存步骤。
 *
 * Args:
 *   steps: 可能包含断档的缓存步骤。
 *
 * Returns:
 *   连续步骤前缀，断档后的步骤会被丢弃。
 */
export function trimCachedStepsToPrefix(steps: AICreateCachedSteps): AICreateCachedSteps {
  const trimmed: AICreateCachedSteps = {};
  for (const step of STEP_ORDER) {
    if (!steps[step]) {
      break;
    }
    // 后续步骤依赖前序结果，断档之后的数据不能用于续跑。
    trimmed[step] = steps[step] as never;
  }
  return trimmed;
}

/**
 * 判断缓存中是否存在至少一个已完成步骤。
 *
 * Args:
 *   steps: 当前缓存步骤。
 *
 * Returns:
 *   任意步骤存在时返回 true。
 */
export function hasAICreateCachedSteps(steps: AICreateCachedSteps): boolean {
  return STEP_ORDER.some((step) => Boolean(steps[step]));
}
