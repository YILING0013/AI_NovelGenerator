/* eslint-disable @next/next/no-img-element */
"use client";

import { useState, useEffect, useRef } from "react";
import { useTranslations } from "next-intl";
import { Button } from "@heroui/react";
import TagInput from "@/components/shared/TagInput";
import { apiPost, apiPutForm } from "@/lib/api";
import type {
  CreateNovelRequest,
  NovelCreateResponse,
  NovelDetail,
  NovelManualCreateRequest,
} from "@/types/novel";

interface NovelFormProps {
  defaults: Partial<CreateNovelRequest>;
  onCreated: (novelId: string, coverUploadFailed: boolean) => void;
  onBack?: () => void;
}

const INPUT_CLASS =
  "min-h-11 w-full rounded-xl border border-border bg-background/80 px-3.5 py-2.5 text-sm text-foreground outline-none transition-[border-color,box-shadow] focus:border-accent focus:ring-2 focus:ring-accent/15";
const TEXTAREA_CLASS =
  "min-h-24 w-full resize-y rounded-xl border border-border bg-background/80 px-3.5 py-2.5 text-sm leading-6 text-foreground outline-none transition-[border-color,box-shadow] focus:border-accent focus:ring-2 focus:ring-accent/15";

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
    plot: "",
    tone: "",
    target_audience: "",
    core_idea: "",
    number_of_chapters: undefined,
    words_per_chapter: undefined,
  });
  const [coverFile, setCoverFile] = useState<File | null>(null);
  const [coverPreview, setCoverPreview] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);
  const idempotencyRef = useRef<{ signature: string; key: string } | null>(null);

  useEffect(() => {
    if (defaults) {
      setForm((prev) => ({ ...prev, ...defaults }));
    }
  }, [defaults]);

  useEffect(() => {
    if (!coverFile || typeof URL.createObjectURL !== "function") {
      setCoverPreview("");
      return;
    }
    const preview = URL.createObjectURL(coverFile);
    setCoverPreview(preview);
    return () => URL.revokeObjectURL(preview);
  }, [coverFile]);

  const updateField = <K extends keyof CreateNovelRequest>(
    key: K,
    value: CreateNovelRequest[K]
  ) => {
    setForm((prev) => ({ ...prev, [key]: value }));
  };

  const handleCoverSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    if (file.size > 2 * 1024 * 1024) {
      setError(tc("coverTooLarge"));
      e.target.value = "";
      return;
    }
    setError("");
    setCoverFile(file);
  };

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!form.title.trim()) return;

    const { genre, ...otherFields } = form;
    const payload: NovelManualCreateRequest = {
      ...otherFields,
      ...(genre?.trim() ? { genre: genre.trim() } : {}),
      request_type: "manual",
      title: form.title.trim(),
    };
    const signature = JSON.stringify(payload);
    if (idempotencyRef.current?.signature !== signature) {
      idempotencyRef.current = {
        signature,
        key: globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random()}`,
      };
    }

    try {
      setSaving(true);
      setError("");
      const created = await apiPost<NovelCreateResponse>("/api/novels/create", payload, {
        headers: { "Idempotency-Key": idempotencyRef.current.key },
      });
      let coverUploadFailed = false;
      if (coverFile) {
        const coverData = new FormData();
        coverData.append("file", coverFile);
        coverData.append("expected_version", String(created.version));
        try {
          await apiPutForm<NovelDetail>(`/api/novels/${created.id}/cover`, coverData);
        } catch {
          coverUploadFailed = true;
        }
      }
      onCreated(created.id, coverUploadFailed);
    } catch (err) {
      setError(err instanceof Error ? err.message : tc("createFailed"));
    } finally {
      setSaving(false);
    }
  };

  return (
    <form className="flex h-full min-h-0 flex-col overflow-hidden" onSubmit={handleSubmit}>
      <div className="workspace-scrollbar min-h-0 flex-1 space-y-5 overflow-y-auto px-4 py-5 sm:px-6 outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-accent/30" tabIndex={0} aria-label={tc("tabManual")}>
        <div className="flex gap-4">
          <div className="shrink-0">
            <label className="block text-sm font-medium text-foreground mb-2">
              {t("coverImage")}
            </label>
            <div className="flex items-start gap-4">
              {coverPreview ? (
                <div className="relative">
                  <img
                    src={coverPreview}
                    alt={t("coverImage")}
                    className="h-32 w-24 rounded-2xl object-cover"
                  />
                  <button
                    type="button"
                    className="absolute -right-2 -top-2 grid h-7 w-7 place-items-center rounded-full bg-red-600 text-sm text-white transition-colors hover:bg-red-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-500"
                    aria-label={t("removeCover")}
                    onClick={() => {
                      setCoverFile(null);
                      if (fileInputRef.current) fileInputRef.current.value = "";
                    }}
                  >
                    ×
                  </button>
                </div>
              ) : (
                <button
                  type="button"
                  className="flex h-32 w-24 items-center justify-center rounded-2xl border border-dashed border-border text-muted transition-colors hover:border-accent hover:text-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/30"
                  aria-label={t("uploadCover")}
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
                accept="image/jpeg,image/png,image/webp"
                className="hidden"
                onChange={handleCoverSelect}
              />
            </div>
          </div>

          <div className="flex-1 min-w-0 space-y-3">
            <FormField label={t("title")} required>
              <input
                type="text"
                className={INPUT_CLASS}
                value={form.title}
                onChange={(e) => updateField("title", e.target.value)}
              />
            </FormField>

            <FormField label={t("subtitle")}>
              <input
                type="text"
                className={INPUT_CLASS}
                value={form.subtitle ?? ""}
                onChange={(e) => updateField("subtitle", e.target.value)}
              />
            </FormField>

            <FormField label={t("genre")}>
              <input
                type="text"
                className={INPUT_CLASS}
                value={form.genre ?? ""}
                onChange={(e) => updateField("genre", e.target.value)}
              />
            </FormField>
          </div>
        </div>

        <TagInput
          label={t("tags")}
          values={form.tags ?? []}
          onChange={(tags) => updateField("tags", tags)}
          getRemoveAriaLabel={(tag) => tc("removeTag", { tag })}
          placeholder={tc("tagPlaceholder")}
          maxItems={5}
          limitReachedText={tc("tagLimitReached")}
        />

        <FormField label={t("introduction")}>
          <textarea
            className={TEXTAREA_CLASS}
            value={form.introduction ?? ""}
            onChange={(e) => updateField("introduction", e.target.value)}
          />
        </FormField>

        <FormField label={t("plot")}>
          <textarea
            className={TEXTAREA_CLASS}
            value={form.plot ?? ""}
            onChange={(e) => updateField("plot", e.target.value)}
          />
        </FormField>

        <FormField label={t("coreIdea")}>
          <textarea
            className={TEXTAREA_CLASS}
            value={form.core_idea ?? ""}
            onChange={(e) => updateField("core_idea", e.target.value)}
          />
        </FormField>

        <div className="grid gap-4 sm:grid-cols-2">
          <FormField label={t("tone")}>
            <input
              type="text"
              className={INPUT_CLASS}
              value={form.tone ?? ""}
              onChange={(e) => updateField("tone", e.target.value)}
            />
          </FormField>
          <FormField label={t("targetAudience")}>
            <input
              type="text"
              className={INPUT_CLASS}
              value={form.target_audience ?? ""}
              onChange={(e) => updateField("target_audience", e.target.value)}
            />
          </FormField>
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <FormField label={t("numberOfChapters")}>
            <input
              type="number"
              className={INPUT_CLASS}
              value={form.number_of_chapters ?? ""}
              onChange={(e) => updateField("number_of_chapters", e.target.value ? Number(e.target.value) : undefined)}
              min={1}
              max={10000}
            />
          </FormField>
          <FormField label={t("wordsPerChapter")}>
            <input
              type="number"
              className={INPUT_CLASS}
              value={form.words_per_chapter ?? ""}
              onChange={(e) => updateField("words_per_chapter", e.target.value ? Number(e.target.value) : undefined)}
              min={500}
              max={50000}
            />
          </FormField>
        </div>

        <FormField label={t("summary")}>
          <textarea
            className={TEXTAREA_CLASS}
            value={form.summary ?? ""}
            onChange={(e) => updateField("summary", e.target.value)}
          />
        </FormField>

        <FormField label={t("coreSeed")}>
          <textarea
            className={TEXTAREA_CLASS}
            value={form.core_seed ?? ""}
            onChange={(e) => updateField("core_seed", e.target.value)}
          />
        </FormField>

        <FormField label={t("worldview")}>
          <textarea
            className={TEXTAREA_CLASS}
            value={form.worldview ?? ""}
            onChange={(e) => updateField("worldview", e.target.value)}
          />
        </FormField>

        <div className="grid gap-4 md:grid-cols-3">
          <FormField label={t("writingStyle")}>
            <input
              type="text"
              className={INPUT_CLASS}
              value={form.writing_style ?? ""}
              onChange={(e) => updateField("writing_style", e.target.value)}
            />
          </FormField>

          <FormField label={t("narrativePov")}>
            <select
              className={INPUT_CLASS}
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
              className={INPUT_CLASS}
              value={form.era_background ?? ""}
              onChange={(e) => updateField("era_background", e.target.value)}
            />
          </FormField>
        </div>

        {error && (
          <p role="alert" className="border-l-2 border-red-500 pl-3 text-sm text-red-700 dark:text-red-300">
            {error}
          </p>
        )}

      </div>
      <div className="flex shrink-0 flex-wrap gap-3 border-t border-border bg-surface px-4 py-4 sm:px-6">
        <Button
          type="submit"
          variant="primary"
          className="min-w-40 flex-1 bg-accent text-accent-foreground hover:bg-accent-hover"
          isDisabled={saving || !form.title.trim()}
        >
          {saving ? tc("creating") : tc("saveNovel")}
        </Button>
        {onBack && (
          <Button type="button" variant="ghost" onPress={onBack} isDisabled={saving}>
            {tc("back")}
          </Button>
        )}
      </div>
    </form>
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
    <label className="grid gap-2 text-sm">
      <span className="font-semibold text-muted">
        {label}
        {required && <span className="ml-0.5 text-red-600 dark:text-red-300">*</span>}
      </span>
      {children}
    </label>
  );
}
