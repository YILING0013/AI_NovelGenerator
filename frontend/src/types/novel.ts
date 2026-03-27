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
  worldview?: string;
  writing_style?: string;
  narrative_pov?: string;
  era_background?: string;
}

export interface CreateNovelRequest {
  title: string;
  subtitle?: string;
  genre?: string;
  tags?: string[];
  introduction?: string;
  worldview?: string;
  writing_style?: string;
  narrative_pov?: string;
  era_background?: string;
  cover_image?: string;
}

export interface AICreateRequest {
  user_idea: string;
  number_of_chapters?: number;
  words_per_chapter?: number;
}

export interface AICreateStepResult {
  step: string;
  data: Record<string, unknown>;
}

export interface AICreateResponse {
  extract_idea: {
    plot: string;
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
    summary: string;
    worldview: string;
    writing_style: string;
    narrative_pov: string;
    era_background: string;
    tags: string[];
  };
}
