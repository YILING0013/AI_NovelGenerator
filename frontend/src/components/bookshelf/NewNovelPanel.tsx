"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { useRouter, usePathname } from "next/navigation";
import { Card, Button } from "@heroui/react";
import AICreateStepper from "./AICreateStepper";
import type { AICreateResponse, WritingDraft } from "@/types/novel";

const DRAFT_KEY = "writing_draft";

interface NewNovelPanelProps {
  onCreated: (novelId: string) => void;
  onCancel: () => void;
}

export default function NewNovelPanel({ onCancel }: NewNovelPanelProps) {
  const t = useTranslations("create");
  const tb = useTranslations("bookshelf");
  const router = useRouter();
  const pathname = usePathname();
  const locale = pathname.startsWith("/en") ? "en" : "zh";
  const [redirecting, setRedirecting] = useState(false);

  const handleAIComplete = (result: AICreateResponse, chapters: number, wordsPerChapter: number) => {
    const meta = result.novel_meta;
    const plot = result.expand_idea?.plot ?? result.extract_idea.plot ?? "";
    const draft: WritingDraft = {
      _fromAI: true,
      title: meta.title,
      subtitle: meta.subtitle,
      genre: result.extract_idea.genre,
      tags: meta.tags,
      introduction: meta.introduction,
      summary: meta.summary,
      core_seed: result.core_seed.core_seed,
      worldview: meta.worldview,
      writing_style: meta.writing_style,
      narrative_pov: meta.narrative_pov,
      era_background: meta.era_background,
      plot,
      tone: result.extract_idea.tone,
      target_audience: result.extract_idea.target_audience,
      core_idea: result.extract_idea.core_idea,
      number_of_chapters: chapters,
      words_per_chapter: wordsPerChapter,
    };
    sessionStorage.setItem(DRAFT_KEY, JSON.stringify(draft));
    setRedirecting(true);
    router.push(`/${locale}/writing/new`);
  };

  return (
    <div className="h-full flex flex-col">
      <Card className="h-full flex flex-col overflow-hidden">
        <Card.Header className="shrink-0">
          <div className="flex items-center justify-between w-full">
            <h2 className="text-lg font-bold text-foreground">{t("title")}</h2>
            <Button variant="ghost" size="sm" onPress={onCancel}>
              {t("back")}
            </Button>
          </div>
        </Card.Header>

        <Card.Content className="flex-1 overflow-y-auto">
          {redirecting ? (
            <div className="flex items-center justify-center h-32">
              <p className="text-sm text-muted">{tb("aiCompleteRedirect")}</p>
            </div>
          ) : (
            <AICreateStepper onComplete={handleAIComplete} />
          )}
        </Card.Content>
      </Card>
    </div>
  );
}
