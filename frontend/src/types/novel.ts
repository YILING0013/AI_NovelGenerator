export interface NovelSummary {
  _id: string;
  title: string;
  subtitle?: string;
  genre: string;
  tags: string[];
  cover_image?: string;
  status: string;
  stats: {
    chapter_count: number;
    total_word_count: number;
  };
  created_at: string;
  updated_at: string;
}

export interface NovelDetail extends NovelSummary {
  introduction?: string;
  summary?: string;
  core_seed?: string;
  worldview?: string;
  writing_style?: string;
  narrative_pov?: string;
  era_background?: string;
  plot?: string;
  tone?: string;
  target_audience?: string;
  core_idea?: string;
  number_of_chapters?: number;
  words_per_chapter?: number;
}

export interface CreateNovelRequest {
  title: string;
  subtitle?: string;
  genre?: string;
  tags?: string[];
  introduction?: string;
  summary?: string;
  core_seed?: string;
  worldview?: string;
  writing_style?: string;
  narrative_pov?: string;
  era_background?: string;
  cover_image?: string;
  plot?: string;
  tone?: string;
  target_audience?: string;
  core_idea?: string;
  number_of_chapters?: number;
  words_per_chapter?: number;
}

export interface AICreateRequest {
  user_idea: string;
  number_of_chapters?: number;
  words_per_chapter?: number;
  // 可选生成参数
  temperature?: number | null;
  top_p?: number | null;
  max_tokens?: number | null;
  presence_penalty?: number | null;
  frequency_penalty?: number | null;
  system_prompt?: string | null;
}

export interface AICreateStepResult {
  step: string;
  data: Record<string, unknown>;
}

export interface AICreateResponse {
  expand_idea?: {
    plot: string;
  };
  extract_idea: {
    plot?: string;
    genre: string;
    tone: string;
    target_audience: string;
    core_idea: string;
  };
  core_seed: {
    core_seed: string;
  };
  novel_meta: {
    title: string;
    subtitle: string;
    introduction: string;
    summary: string;
    worldview: string;
    writing_style: string;
    narrative_pov: string;
    era_background: string;
    tags: string[];
  };
}

/** AI 创建草稿，用于 sessionStorage 传递到 Writing 创建态 */
export interface WritingDraft extends CreateNovelRequest {
  _fromAI?: boolean;
}

/** Writing 侧栏导航项 */
export type WritingSidebarItem =
  | "novel-info"
  | "chapter-editor"
  | "character-cards"
  | "location-cards"
  | "faction-cards"
  | "item-cards"
  | "rule-cards"
  | "relationship-map";
