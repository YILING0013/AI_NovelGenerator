/* eslint-disable @next/next/no-img-element */
"use client";

import { useState, useEffect, useRef } from "react";
import { useTranslations } from "next-intl";
import { Button } from "@heroui/react";
import { apiPost, apiPostForm, getImageUrl } from "@/lib/api";
import type { CreateNovelRequest } from "@/types/novel";

interface NovelFormProps {
  defaults: Partial<CreateNovelRequest>;
  onCreated: (novelId: string) => void;
  onBack?: () => void;
}

export default function NovelForm({ defaults, onCreated, onBack }: NovelFormProps) {
  const t = useTranslations("novel");
  const tc = useTranslations("create");
  const [form, setForm] = useState<CreateNovelRequest>({
    title: "",
    subtitle: "",
    genre: "",
    tags: [],
    introduction: "",
    summary: "",
    core_seed: "",
    worldview: "",
    writing_style: "",
    narrative_pov: "",
    era_background: "",
    cover_image: "",
    plot: "",
    tone: "",
    target_audience: "",
    core_idea: "",
    number_of_chapters: undefined,
    words_per_chapter: undefined,
  });
  const [tagInput, setTagInput] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (defaults) {
      setForm((prev) => ({ ...prev, ...defaults }));
      if (defaults.tags) {
        setTagInput(defaults.tags.join(", "));
      }
    }
  }, [defaults]);

  const updateField = <K extends keyof CreateNovelRequest>(
    key: K,
    value: CreateNovelRequest[K]
  ) => {
    setForm((prev) => ({ ...prev, [key]: value }));
  };

  const handleCoverUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    if (file.size > 2 * 1024 * 1024) {
      setError(t("coverTooLarge") || "File too large");
      return;
    }

    try {
      const formData = new FormData();
      formData.append("file", file);
      const res = await apiPostForm<{ url: string }>("/api/upload/cover", formData);
      updateField("cover_image", res.url);
    } catch (err) {
      console.error(err);
      setError("Upload failed");
    }
  };

  const handleSubmit = async () => {
    if (!form.title.trim()) return;

    const tags = tagInput
      .split(/[,，]/)
      .map((s) => s.trim())
      .filter(Boolean);

    try {
      setSaving(true);
      setError("");
      const res = await apiPost<{ id: string }>("/api/novels/create", {
        ...form,
        tags,
      });
      onCreated(res.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : tc("createFailed"));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-4 p-1">
      {/* Cover + Title/Subtitle/Genre Row */}
      <div className="flex gap-4">
        {/* Left: Cover Upload */}
        <div className="shrink-0">
          <label className="block text-sm font-medium text-foreground mb-2">
            {t("coverImage")}
          </label>
          <div className="flex items-start gap-4">
            {form.cover_image ? (
              <div className="relative">
                <img
                  src={getImageUrl(form.cover_image)}
                  alt="Cover"
                  className="w-24 h-32 rounded-lg object-cover shadow-sm"
                />
                <button
                  className="absolute -top-2 -right-2 w-5 h-5 rounded-full bg-red-500 text-white text-xs flex items-center justify-center hover:bg-red-600"
                  onClick={() => updateField("cover_image", "")}
                >
                  ✕
                </button>
              </div>
            ) : (
              <button
                className="w-24 h-32 rounded-lg border-2 border-dashed border-border hover:border-primary flex items-center justify-center text-muted hover:text-primary transition-colors"
                onClick={() => fileInputRef.current?.click()}
              >
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  width="24"
                  height="24"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.5"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <path d="M12 5v14M5 12h14" />
                </svg>
              </button>
            )}
            <input
              ref={fileInputRef}
              type="file"
              accept="image/*"
              className="hidden"
              onChange={handleCoverUpload}
            />
          </div>
        </div>

        {/* Right: Title / Subtitle / Genre */}
        <div className="flex-1 min-w-0 space-y-3">
          <FormField label={t("title")} required>
            <input
              type="text"
              className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
              value={form.title}
              onChange={(e) => updateField("title", e.target.value)}
            />
          </FormField>

          <FormField label={t("subtitle")}>
            <input
              type="text"
              className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
              value={form.subtitle ?? ""}
              onChange={(e) => updateField("subtitle", e.target.value)}
            />
          </FormField>

          <FormField label={t("genre")}>
            <input
              type="text"
              className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
              value={form.genre ?? ""}
              onChange={(e) => updateField("genre", e.target.value)}
            />
          </FormField>
        </div>
      </div>

      {/* Tags */}
      <FormField label={t("tags")}>
        <input
          type="text"
          className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
          placeholder="tag1, tag2, tag3"
          value={tagInput}
          onChange={(e) => setTagInput(e.target.value)}
        />
      </FormField>

      {/* Introduction */}
      <FormField label={t("introduction")}>
        <textarea
          className="w-full rounded-lg border border-border bg-background p-3 text-sm text-foreground resize-y min-h-[80px] focus:outline-none focus:ring-2 focus:ring-primary"
          value={form.introduction ?? ""}
          onChange={(e) => updateField("introduction", e.target.value)}
        />
      </FormField>

      {/* Plot */}
      <FormField label={t("plot")}>
        <textarea
          className="w-full rounded-lg border border-border bg-background p-3 text-sm text-foreground resize-y min-h-[80px] focus:outline-none focus:ring-2 focus:ring-primary"
          value={form.plot ?? ""}
          onChange={(e) => updateField("plot", e.target.value)}
        />
      </FormField>

      {/* Core Idea */}
      <FormField label={t("coreIdea")}>
        <textarea
          className="w-full rounded-lg border border-border bg-background p-3 text-sm text-foreground resize-y min-h-[60px] focus:outline-none focus:ring-2 focus:ring-primary"
          value={form.core_idea ?? ""}
          onChange={(e) => updateField("core_idea", e.target.value)}
        />
      </FormField>

      {/* Tone / Target Audience Row */}
      <div className="grid grid-cols-2 gap-4">
        <FormField label={t("tone")}>
          <input
            type="text"
            className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
            value={form.tone ?? ""}
            onChange={(e) => updateField("tone", e.target.value)}
          />
        </FormField>
        <FormField label={t("targetAudience")}>
          <input
            type="text"
            className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
            value={form.target_audience ?? ""}
            onChange={(e) => updateField("target_audience", e.target.value)}
          />
        </FormField>
      </div>

      {/* Chapters / Words per Chapter Row */}
      <div className="grid grid-cols-2 gap-4">
        <FormField label={t("numberOfChapters")}>
          <input
            type="number"
            className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
            value={form.number_of_chapters ?? ""}
            onChange={(e) => updateField("number_of_chapters", e.target.value ? Number(e.target.value) : undefined)}
            min={1}
            max={10000}
          />
        </FormField>
        <FormField label={t("wordsPerChapter")}>
          <input
            type="number"
            className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
            value={form.words_per_chapter ?? ""}
            onChange={(e) => updateField("words_per_chapter", e.target.value ? Number(e.target.value) : undefined)}
            min={500}
            max={50000}
          />
        </FormField>
      </div>

      {/* Summary */}
      <FormField label={t("summary")}>
        <textarea
          className="w-full rounded-lg border border-border bg-background p-3 text-sm text-foreground resize-y min-h-[80px] focus:outline-none focus:ring-2 focus:ring-primary"
          value={form.summary ?? ""}
          onChange={(e) => updateField("summary", e.target.value)}
        />
      </FormField>

      {/* Core Seed */}
      <FormField label={t("coreSeed")}>
        <textarea
          className="w-full rounded-lg border border-border bg-background p-3 text-sm text-foreground resize-y min-h-[60px] focus:outline-none focus:ring-2 focus:ring-primary"
          value={form.core_seed ?? ""}
          onChange={(e) => updateField("core_seed", e.target.value)}
        />
      </FormField>

      {/* Worldview */}
      <FormField label={t("worldview")}>
        <textarea
          className="w-full rounded-lg border border-border bg-background p-3 text-sm text-foreground resize-y min-h-[80px] focus:outline-none focus:ring-2 focus:ring-primary"
          value={form.worldview ?? ""}
          onChange={(e) => updateField("worldview", e.target.value)}
        />
      </FormField>

      {/* Writing Style / POV / Era - Row */}
      <div className="grid grid-cols-3 gap-4">
        <FormField label={t("writingStyle")}>
          <input
            type="text"
            className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
            value={form.writing_style ?? ""}
            onChange={(e) => updateField("writing_style", e.target.value)}
          />
        </FormField>

        <FormField label={t("narrativePov")}>
          <select
            className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
            value={form.narrative_pov ?? ""}
            onChange={(e) => updateField("narrative_pov", e.target.value)}
          >
            <option value="">--</option>
            <option value="第一人称">{t("povFirst")}</option>
            <option value="第三人称有限视角">{t("povThirdLimited")}</option>
            <option value="全知视角">{t("povOmniscient")}</option>
          </select>
        </FormField>

        <FormField label={t("eraBackground")}>
          <input
            type="text"
            className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
            value={form.era_background ?? ""}
            onChange={(e) => updateField("era_background", e.target.value)}
          />
        </FormField>
      </div>

      {/* Error */}
      {error && (
        <p className="text-sm text-red-500">{error}</p>
      )}

      {/* Actions */}
      <div className="flex gap-3 pt-2">
        <Button
          variant="primary"
          className="flex-1"
          isDisabled={saving || !form.title.trim()}
          onPress={handleSubmit}
        >
          {saving ? tc("generating") : tc("saveNovel")}
        </Button>
        {onBack && (
          <Button variant="ghost" onPress={onBack}>
            {tc("back")}
          </Button>
        )}
      </div>
    </div>
  );
}

function FormField({
  label,
  required,
  children,
}: {
  label: string;
  required?: boolean;
  children: React.ReactNode;
}) {
  return (
    <div>
      <label className="block text-sm font-medium text-foreground mb-1">
        {label}
        {required && <span className="text-red-500 ml-0.5">*</span>}
      </label>
      {children}
    </div>
  );
}
