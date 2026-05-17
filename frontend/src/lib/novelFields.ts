export type SectionKey = "basic" | "creative" | "scale" | "content" | "style";

export type NovelInfoFieldType =
  | "text"
  | "textarea"
  | "number"
  | "tags"
  | "cover"
  | "select";

export interface NovelInfoFieldDef {
  key: string;
  type: NovelInfoFieldType;
  options?: { value: string; labelKey: string }[];
}

export const NARRATIVE_POV_OPTIONS = [
  { value: "第一人称", labelKey: "povFirst" },
  { value: "第三人称有限视角", labelKey: "povThirdLimited" },
  { value: "全知视角", labelKey: "povOmniscient" },
] as const;

export const SECTION_FIELDS: Record<SectionKey, NovelInfoFieldDef[]> = {
  basic: [
    { key: "title", type: "text" },
    { key: "subtitle", type: "text" },
    { key: "genre", type: "text" },
    { key: "tags", type: "tags" },
    { key: "cover_image", type: "cover" },
  ],
  creative: [
    { key: "plot", type: "textarea" },
    { key: "core_idea", type: "textarea" },
    { key: "tone", type: "text" },
    { key: "target_audience", type: "text" },
  ],
  scale: [
    { key: "number_of_chapters", type: "number" },
    { key: "words_per_chapter", type: "number" },
  ],
  content: [
    { key: "introduction", type: "textarea" },
    { key: "summary", type: "textarea" },
    { key: "core_seed", type: "textarea" },
    { key: "worldview", type: "textarea" },
  ],
  style: [
    { key: "writing_style", type: "textarea" },
    { key: "narrative_pov", type: "select", options: [...NARRATIVE_POV_OPTIONS] },
    { key: "era_background", type: "textarea" },
  ],
};

export const LONG_TEXT_FIELDS = new Set([
  "introduction",
  "plot",
  "core_idea",
  "summary",
  "core_seed",
  "worldview",
  "writing_style",
  "era_background",
]);

export const DANGEROUS_FIELDS = new Set([
  "plot",
  "core_idea",
  "summary",
  "core_seed",
  "worldview",
  "writing_style",
  "narrative_pov",
  "era_background",
]);

export const FIELD_LABEL_MAP: Record<string, string> = {
  title: "title",
  subtitle: "subtitle",
  genre: "genre",
  tags: "tags",
  cover_image: "coverImage",
  plot: "plot",
  core_idea: "coreIdea",
  tone: "tone",
  target_audience: "targetAudience",
  number_of_chapters: "numberOfChapters",
  words_per_chapter: "wordsPerChapter",
  introduction: "introduction",
  summary: "summary",
  core_seed: "coreSeed",
  worldview: "worldview",
  writing_style: "writingStyle",
  narrative_pov: "narrativePov",
  era_background: "eraBackground",
};

export const REWRITABLE_NOVEL_FIELDS = [
  "title",
  "subtitle",
  "genre",
  "tags",
  "plot",
  "core_idea",
  "tone",
  "target_audience",
  "introduction",
  "summary",
  "core_seed",
  "worldview",
  "writing_style",
  "narrative_pov",
  "era_background",
] as const;

export type NovelRewriteFieldKey = (typeof REWRITABLE_NOVEL_FIELDS)[number];

export const CREATE_NOVEL_CONTEXT_FIELDS = [
  ...REWRITABLE_NOVEL_FIELDS,
  "number_of_chapters",
  "words_per_chapter",
] as const;

/**
 * 判断给定字段是否支持创建态 AI 改写。
 *
 * Args:
 *   key: 需要检查的字段名。
 *
 * Returns:
 *   支持 AI 改写时返回 true，否则返回 false。
 */
export function isNovelRewriteFieldKey(key: string): key is NovelRewriteFieldKey {
  return (REWRITABLE_NOVEL_FIELDS as readonly string[]).includes(key);
}
