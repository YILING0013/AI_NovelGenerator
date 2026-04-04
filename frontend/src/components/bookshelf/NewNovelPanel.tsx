"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { Card, Button } from "@heroui/react";
import AICreateStepper from "./AICreateStepper";
import NovelForm from "./NovelForm";
import type { CreateNovelRequest } from "@/types/novel";
import type { AICreateResponse } from "@/types/novel";

interface NewNovelPanelProps {
  onCreated: (novelId: string) => void;
  onCancel: () => void;
}

type Tab = "ai" | "manual";

export default function NewNovelPanel({ onCreated, onCancel }: NewNovelPanelProps) {
  const t = useTranslations("create");
  const [tab, setTab] = useState<Tab>("ai");
  const [aiResult, setAiResult] = useState<AICreateResponse | null>(null);
  const [showForm, setShowForm] = useState(false);

  const handleAIComplete = (result: AICreateResponse) => {
    setAiResult(result);
    setShowForm(true);
  };

  const getFormDefaults = (): Partial<CreateNovelRequest> => {
    if (!aiResult) return {};
    const meta = aiResult.novel_meta;
    return {
      title: meta.title,
      subtitle: meta.subtitle,
      genre: aiResult.extract_idea.genre,
      tags: meta.tags,
      introduction: meta.introduction,
      summary: meta.summary,
      core_seed: aiResult.core_seed.core_seed,
      worldview: meta.worldview,
      writing_style: meta.writing_style,
      narrative_pov: meta.narrative_pov,
      era_background: meta.era_background,
    };
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
          {/* Tabs */}
          {!showForm && (
            <div className="flex gap-1 mb-6 border-b border-border">
              <button
                className={`px-4 py-2 text-sm font-medium transition-colors border-b-2 -mb-px ${tab === "ai"
                    ? "border-primary text-primary"
                    : "border-transparent text-muted hover:text-foreground"
                  }`}
                onClick={() => setTab("ai")}
              >
                {t("tabAI")}
              </button>
              <button
                className={`px-4 py-2 text-sm font-medium transition-colors border-b-2 -mb-px ${tab === "manual"
                    ? "border-primary text-primary"
                    : "border-transparent text-muted hover:text-foreground"
                  }`}
                onClick={() => setTab("manual")}
              >
                {t("tabManual")}
              </button>
            </div>
          )}

          {showForm ? (
            <div>
              {aiResult && (
                <div className="mb-4 p-3 rounded-lg bg-primary/5 border border-primary/20">
                  <h3 className="text-sm font-semibold text-primary mb-1">
                    {t("reviewTitle")}
                  </h3>
                  <p className="text-xs text-muted">{t("reviewDescription")}</p>
                </div>
              )}
              <NovelForm
                defaults={getFormDefaults()}
                onCreated={onCreated}
                onBack={() => {
                  setShowForm(false);
                  setAiResult(null);
                }}
              />
            </div>
          ) : tab === "ai" ? (
            <AICreateStepper onComplete={handleAIComplete} />
          ) : (
            <NovelForm defaults={{}} onCreated={onCreated} />
          )}
        </Card.Content>
      </Card>
    </div>
  );
}
