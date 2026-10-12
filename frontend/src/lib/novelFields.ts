export type SectionKey = "basic" | "creative" | "content" | "style";

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
  hintKey?: string;
  recommendedMinLength?: number;
  recommendedMaxLength?: number;
  minHeight?: number;
  maxHeight?: number;
  unitKey?: "chapters" | "wordsPerChapter";
}

export const NARRATIVE_POV_OPTIONS = [
  { value: "第一人称", labelKey: "povFirst" },
  { value: "第三人称有限视角", labelKey: "povThirdLimited" },
  { value: "全知视角", labelKey: "povOmniscient" },
] as const;

export const SECTION_FIELDS: Record<SectionKey, NovelInfoFieldDef[]> = {
  basic: [
    { key: "title", type: "text", hintKey: "title", recommendedMaxLength: 30 },
    { key: "subtitle", type: "text", hintKey: "subtitle", recommendedMaxLength: 50 },
    { key: "genre", type: "text", hintKey: "genre", recommendedMaxLength: 30 },
    { key: "tags", type: "tags", hintKey: "tags" },
    { key: "cover_image", type: "cover" },
    // 篇幅参数属于作品的基础规格，与识别信息一起编辑可减少独立短章节的空间浪费。
    {
      key: "number_of_chapters",
      type: "number",
      hintKey: "numberOfChapters",
      unitKey: "chapters",
    },
    {
      key: "words_per_chapter",
      type: "number",
      hintKey: "wordsPerChapter",
      unitKey: "wordsPerChapter",
    },
  ],
  creative: [
    {
      key: "plot",
      type: "textarea",
      hintKey: "plot",
      recommendedMinLength: 200,
      recommendedMaxLength: 5000,
      minHeight: 280,
      maxHeight: 560,
    },
    {
      key: "core_idea",
      type: "textarea",
      hintKey: "coreIdea",
      recommendedMinLength: 10,
      recommendedMaxLength: 300,
      minHeight: 144,
      maxHeight: 280,
    },
    { key: "tone", type: "text", hintKey: "tone", recommendedMaxLength: 30 },
    {
      key: "target_audience",
      type: "text",
      hintKey: "targetAudience",
      recommendedMaxLength: 30,
    },
  ],
  content: [
    {
      key: "introduction",
      type: "textarea",
      hintKey: "introduction",
      recommendedMinLength: 100,
      recommendedMaxLength: 300,
      minHeight: 160,
      maxHeight: 320,
    },
    {
      key: "summary",
      type: "textarea",
      hintKey: "summary",
      recommendedMinLength: 100,
      recommendedMaxLength: 500,
      minHeight: 190,
      maxHeight: 380,
    },
    {
      key: "core_seed",
      type: "textarea",
      hintKey: "coreSeed",
      recommendedMinLength: 30,
      recommendedMaxLength: 150,
      minHeight: 132,
      maxHeight: 260,
    },
    {
      key: "worldview",
      type: "textarea",
      hintKey: "worldview",
      recommendedMinLength: 100,
      recommendedMaxLength: 800,
      minHeight: 230,
      maxHeight: 460,
    },
  ],
  style: [
    {
      key: "writing_style",
      type: "text",
      hintKey: "writingStyle",
      recommendedMaxLength: 50,
    },
    {
      key: "era_background",
      type: "text",
      hintKey: "eraBackground",
      recommendedMaxLength: 50,
    },
    {
      key: "narrative_pov",
      type: "select",
      hintKey: "narrativePov",
      options: [...NARRATIVE_POV_OPTIONS],
    },
  ],
};

export const LONG_TEXT_FIELDS = new Set([
  "introduction",
  "plot",
  "core_idea",
  "summary",
  "core_seed",
  "worldview",
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
