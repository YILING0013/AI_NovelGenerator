"use client";
import { useAssistantResource } from "@/components/writing/assistant/AssistantContext";

import { useEffect, useId, useState } from "react";
import { useTranslations } from "next-intl";
import { Button } from "@heroui/react";
import SectionEditButton from "@/components/shared/SectionEditButton";
import TagInput from "@/components/shared/TagInput";
import AutoResizeTextarea from "./AutoResizeTextarea";
import CollapsibleField from "./CollapsibleField";
import { apiDelete, apiPut, apiPutForm, getImageUrl } from "@/lib/api";
import type { NovelDetail, NovelUpdateRequest } from "@/types/novel";
import {
  DANGEROUS_FIELDS,
  FIELD_LABEL_MAP,
  LONG_TEXT_FIELDS,
  SECTION_FIELDS,
  type NovelInfoFieldDef,
  type SectionKey,
} from "@/lib/novelFields";

export type { SectionKey } from "@/lib/novelFields";

interface NovelInfoSectionProps {
  sectionKey: SectionKey;
  data: Record<string, unknown>;
  novelId?: string;
  isCreateMode: boolean;
  isEditing: boolean;
  onStartEdit: () => void;
  onCancelEdit: () => void;
  onSaved: (novel: NovelDetail) => void;
  onNovelChanged: (novel: NovelDetail) => void;
  onChange?: (field: string, value: unknown) => void;
  hasChapters?: boolean;
  onDangerConfirm?: () => Promise<boolean>;
  editLocked?: boolean;
  onCoverUploadStateChange?: (uploading: boolean) => void;
  createCoverFile?: File | null;
  onCreateCoverChange?: (file: File | null) => void;
}

const SECTION_NUMBER: Record<SectionKey, string> = {
  basic: "01",
  creative: "02",
  content: "03",
  style: "04",
};

const FIELD_LAYOUT_CLASSES: Record<SectionKey, Record<string, string>> = {
  basic: {
    title: "@[900px]/novel-info:col-start-4 @[900px]/novel-info:col-span-9 @[900px]/novel-info:row-start-1",
    subtitle: "@[900px]/novel-info:col-start-4 @[900px]/novel-info:col-span-9 @[900px]/novel-info:row-start-2",
    genre: "@[900px]/novel-info:col-start-4 @[900px]/novel-info:col-span-4 @[900px]/novel-info:row-start-3",
    tags: "@[900px]/novel-info:col-start-8 @[900px]/novel-info:col-span-5 @[900px]/novel-info:row-start-3",
    cover_image: "@[900px]/novel-info:col-start-1 @[900px]/novel-info:col-span-3 @[900px]/novel-info:row-start-1 @[900px]/novel-info:row-span-4",
    number_of_chapters: "@[900px]/novel-info:col-start-4 @[900px]/novel-info:col-span-4 @[900px]/novel-info:row-start-4",
    words_per_chapter: "@[900px]/novel-info:col-start-8 @[900px]/novel-info:col-span-5 @[900px]/novel-info:row-start-4",
  },
  creative: {},
  content: {
    introduction: "@[900px]/novel-info:col-span-5",
    summary: "@[900px]/novel-info:col-span-7",
    core_seed: "@[900px]/novel-info:col-span-4",
    worldview: "@[900px]/novel-info:col-span-8",
  },
  style: {
    writing_style: "@[900px]/novel-info:col-span-6",
    era_background: "@[900px]/novel-info:col-span-6",
    narrative_pov: "@[900px]/novel-info:col-span-12",
  },
};

const FIELD_GRID_CLASS = "grid min-w-0 grid-cols-1 gap-x-6 @[900px]/novel-info:grid-cols-12";
const CONTROL_CLASS =
  "w-full rounded-xl border border-border bg-background/80 px-3 py-2.5 text-sm text-foreground outline-none transition-[border-color,box-shadow] placeholder:text-muted/50 focus:border-accent focus:ring-2 focus:ring-accent/15";
const READ_FIELD_CLASS = "grid min-w-0 content-start gap-2";
const READ_LABEL_CLASS = "block text-xs font-medium leading-5 text-muted";
const READ_VALUE_CLASS = "reading-copy block min-w-0 break-words text-foreground";

/**
 * 返回字段在章节网格中的布局类。
 *
 * Args:
 *   sectionKey: 字段所属的小说信息章节。
 *   fieldKey: 字段键名。
 *
 * Returns:
 *   对应的响应式网格类；未配置时占满当前行。
 */
function getFieldLayoutClass(sectionKey: SectionKey, fieldKey: string): string {
  return FIELD_LAYOUT_CLASSES[sectionKey][fieldKey] || "col-span-full";
}

/**
 * 把未知标签值收敛为字符串数组。
 *
 * Args:
 *   value: 表单或接口返回的未知值。
 *
 * Returns:
 *   可安全交给标签控件的字符串数组。
 */
function normalizeTagValues(value: unknown): string[] {
  return Array.isArray(value) ? value.map(String) : [];
}

/**
 * 判断未知值是否为可保存的正整数。
 *
 * Args:
 *   value: 需要校验的输入值。
 *
 * Returns:
 *   值为大于 0 的整数时返回 true，否则返回 false。
 */
function isPositiveInteger(value: unknown): value is number {
  return typeof value === "number" && Number.isInteger(value) && value > 0;
}

/**
 * 校验可选的正整数字段，空值保持为合法的“未设置”状态。
 *
 * Args:
 *   value: 需要校验的输入值。
 *
 * Returns:
 *   值为空或为正整数时返回 true，否则返回 false。
 */
function isValidOptionalPositiveInteger(value: unknown): boolean {
  return value === undefined || value === null || value === "" || isPositiveInteger(value);
}

export default function NovelInfoSection({
  sectionKey,
  data,
  novelId,
  isCreateMode,
  isEditing,
  onStartEdit,
  onCancelEdit,
  onSaved,
  onNovelChanged,
  onChange,
  hasChapters = false,
  onDangerConfirm,
  editLocked = false,
  onCoverUploadStateChange,
  createCoverFile = null,
  onCreateCoverChange,
}: NovelInfoSectionProps) {
  const t = useTranslations("novel");
  const tw = useTranslations("writing.novelInfo");
  const fields = SECTION_FIELDS[sectionKey];
  const fieldIdPrefix = useId();

  const [editData, setEditData] = useState<Record<string, unknown>>({});
  const [editVersion, setEditVersion] = useState(() => Number(data.version));
  useAssistantResource(isEditing && novelId && !isCreateMode ? { resource_type: "novel", id: novelId, name: String(data.title ?? ""), version: Number(data.version), draft: { text: JSON.stringify(editData), fields: fields.map((field) => field.key), version: editVersion } } : null);
  const [saving, setSaving] = useState(false);
  const [confirmingDanger, setConfirmingDanger] = useState(false);
  const [saveError, setSaveError] = useState("");
  const [coverError, setCoverError] = useState("");
  const [uploadingCover, setUploadingCover] = useState(false);
  const [createCoverPreview, setCreateCoverPreview] = useState("");

  useEffect(() => {
    if (!createCoverFile || typeof URL.createObjectURL !== "function") {
      setCreateCoverPreview("");
      return;
    }
    const preview = URL.createObjectURL(createCoverFile);
    setCreateCoverPreview(preview);
    return () => URL.revokeObjectURL(preview);
  }, [createCoverFile]);

  const startEdit = () => {
    const snapshot: Record<string, unknown> = {};
    for (const field of fields) {
      // 数字空值必须保留为 undefined，避免进入编辑态后被静默改写成 0。
      snapshot[field.key] =
        data[field.key] ??
        (field.type === "tags" ? [] : field.type === "number" ? undefined : "");
    }
    setEditData(snapshot);
    // 后台刷新可能更新正式资料；旧草稿仍只能按开始编辑时的版本提交。
    setEditVersion(Number(data.version));
    setSaveError("");
    setCoverError("");
    onStartEdit();
  };

  const cancelEdit = () => {
    setEditData({});
    setSaveError("");
    setCoverError("");
    onCancelEdit();
  };

  const hasDangerousChanges = (): boolean => {
    if (!hasChapters) return false;
    return fields.some((field) => {
      if (!DANGEROUS_FIELDS.has(field.key)) return false;
      const originalValue = String(data[field.key] ?? "");
      const editedValue = String(editData[field.key] ?? "");
      return originalValue !== editedValue;
    });
  };

  const saveSection = async () => {
    if (isCreateMode || !novelId) return;

    if (hasDangerousChanges() && onDangerConfirm) {
      setConfirmingDanger(true);
      try {
        const confirmed = await onDangerConfirm();
        if (!confirmed) return;
      } finally {
        setConfirmingDanger(false);
      }
    }

    try {
      setSaving(true);
      setSaveError("");
      const editableFields = Object.fromEntries(
        Object.entries(editData).filter(([key]) => key !== "cover_image"),
      );
      const payload: NovelUpdateRequest = {
        ...editableFields,
        request_type: "manual",
        expected_version: editVersion,
      };
      const result = await apiPut<NovelDetail>(`/api/novels/${novelId}`, payload);
      setEditData({});
      onSaved(result);
    } catch (error) {
      // 保存失败时保留当前编辑快照，让用户可以修正或直接重试。
      setSaveError(error instanceof Error ? error.message : tw("saveFailed"));
    } finally {
      setSaving(false);
    }
  };

  const updateField = (key: string, value: unknown) => {
    if (isCreateMode && onChange) {
      onChange(key, value);
    } else {
      setEditData((previous) => ({ ...previous, [key]: value }));
    }
  };

  const getValue = (key: string): unknown => {
    if (isCreateMode) return data[key];
    if (isEditing) return editData[key];
    return data[key];
  };

  const handleCoverUpload = async (file: File) => {
    setCoverError("");
    if (file.size > 2 * 1024 * 1024) {
      setCoverError(tw("coverTooLarge"));
      return;
    }
    if (isCreateMode) {
      onCreateCoverChange?.(file);
      return;
    }
    if (!novelId) return;
    const formData = new FormData();
    formData.append("file", file);
    formData.append("expected_version", String(data.version));
    setUploadingCover(true);
    onCoverUploadStateChange?.(true);
    try {
      const result = await apiPutForm<NovelDetail>(`/api/novels/${novelId}/cover`, formData);
      setEditData((previous) => ({ ...previous, cover_image: result.cover_image ?? "" }));
      onNovelChanged(result);
    } catch (error) {
      // 上传失败只影响封面字段，保留当前章节的其他编辑内容。
      setCoverError(error instanceof Error ? error.message : tw("coverUploadFailed"));
    } finally {
      setUploadingCover(false);
      onCoverUploadStateChange?.(false);
    }
  };

  const handleCoverRemove = async () => {
    setCoverError("");
    if (isCreateMode) {
      onCreateCoverChange?.(null);
      return;
    }
    if (!novelId) return;
    setUploadingCover(true);
    onCoverUploadStateChange?.(true);
    try {
      const result = await apiDelete<NovelDetail>(`/api/novels/${novelId}/cover`, {
        data: { expected_version: Number(data.version) },
      });
      setEditData((previous) => ({ ...previous, cover_image: "" }));
      onNovelChanged(result);
    } catch (error) {
      setCoverError(error instanceof Error ? error.message : tw("coverRemoveFailed"));
    } finally {
      setUploadingCover(false);
      onCoverUploadStateChange?.(false);
    }
  };

  const renderCharacterCount = (
    field: NovelInfoFieldDef,
    value: unknown,
    supportId: string,
  ) => {
    if (field.recommendedMaxLength === undefined) return null;

    const textValue = String(value ?? "");

    return (
      <div id={supportId} className="flex justify-end text-xs leading-5 text-muted">
        <span
          className={`shrink-0 tabular-nums ${
            textValue.length > field.recommendedMaxLength ? "text-red-600 dark:text-red-300" : ""
          }`}
        >
          {tw("characterCount", {
            count: textValue.length,
            max: field.recommendedMaxLength,
          })}
        </span>
      </div>
    );
  };

  const renderReadField = (
    field: NovelInfoFieldDef,
    layoutClassOverride?: string,
  ) => {
    const value = data[field.key];
    const label = t(FIELD_LABEL_MAP[field.key] || field.key);
    const layoutClass = layoutClassOverride ?? getFieldLayoutClass(sectionKey, field.key);

    if (field.type === "cover") {
      const url = value as string | undefined;
      return (
        <div key={field.key} className={`${layoutClass} ${READ_FIELD_CLASS}`}>
          <span className={READ_LABEL_CLASS}>{label}</span>
          <div className="aspect-[3/4] max-w-44 overflow-hidden rounded-2xl border border-border bg-surface-secondary">
            {url ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={getImageUrl(url)} alt={label} className="h-full w-full object-cover" />
            ) : (
              <div className="grid h-full place-items-center text-xs text-muted/60">{tw("noCover")}</div>
            )}
          </div>
        </div>
      );
    }

    if (field.type === "tags") {
      const tags = normalizeTagValues(value);
      return (
        <div key={field.key} className={`${layoutClass} ${READ_FIELD_CLASS}`}>
          <span className={READ_LABEL_CLASS}>{label}</span>
          <div className="flex flex-wrap gap-2">
            {tags.length > 0 ? (
              tags.map((tag) => (
                <span key={tag} className="rounded-full bg-accent/10 px-2.5 py-1 text-xs font-medium text-accent">
                  {tag}
                </span>
              ))
            ) : (
              <span className="text-sm text-muted/50">—</span>
            )}
          </div>
        </div>
      );
    }

    if (LONG_TEXT_FIELDS.has(field.key)) {
      return (
        <div key={field.key} className={`${layoutClass} min-w-0 self-start`}>
          <CollapsibleField
            label={label}
            value={String(value ?? "")}
            noContentText={tw("noContent")}
          />
        </div>
      );
    }

    if (field.type === "select" && field.options) {
      const display = field.options.find((option) => option.value === value);
      return (
        <div key={field.key} className={`${layoutClass} ${READ_FIELD_CLASS}`}>
          <span className={READ_LABEL_CLASS}>{label}</span>
          <span className={`${READ_VALUE_CLASS} text-[15px]`}>
            {display ? t(display.labelKey) : String(value ?? "—")}
          </span>
        </div>
      );
    }

    const unit = field.unitKey ? tw(`units.${field.unitKey}`) : "";
    const valueClass = field.key === "title"
      ? "text-lg font-semibold tracking-tight"
      : field.type === "number"
        ? "text-base font-semibold tabular-nums"
        : "text-[15px]";
    return (
      <div key={field.key} className={`${layoutClass} ${READ_FIELD_CLASS}`}>
        <span className={READ_LABEL_CLASS}>{label}</span>
        <span className={`${READ_VALUE_CLASS} ${valueClass}`}>
          {value != null && value !== "" ? `${String(value)}${unit ? ` ${unit}` : ""}` : "—"}
        </span>
      </div>
    );
  };

  const renderEditField = (
    field: NovelInfoFieldDef,
    layoutClassOverride?: string,
  ) => {
    const value = getValue(field.key);
    const label = t(FIELD_LABEL_MAP[field.key] || field.key);
    const inputId = `${fieldIdPrefix}-${field.key}`;
    const supportId = `${inputId}-support`;
    const layoutClass = layoutClassOverride ?? getFieldLayoutClass(sectionKey, field.key);

    if (field.type === "cover") {
      const url = isCreateMode ? createCoverPreview : value as string | undefined;
      return (
        <div key={field.key} className={`${layoutClass} space-y-2`}>
          <span className="text-sm font-medium leading-5 text-muted">{label}</span>
          <div className="aspect-[3/4] max-w-44 overflow-hidden rounded-2xl border border-dashed border-border bg-surface-secondary">
            {url ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={isCreateMode ? url : getImageUrl(url)} alt={label} className="h-full w-full object-cover" />
            ) : (
              <label className="relative grid h-full cursor-pointer place-items-center px-4 text-center text-xs leading-5 text-muted transition-colors hover:text-accent focus-within:ring-2 focus-within:ring-inset focus-within:ring-accent">
                <span>{t("uploadCover")}</span>
                <input
                  type="file"
                  accept="image/jpeg,image/png,image/webp"
                  className="absolute inset-0 h-full w-full cursor-pointer opacity-0"
                  aria-label={t("uploadCover")}
                  disabled={uploadingCover}
                  onChange={(event) => {
                    const file = event.target.files?.[0];
                    if (file) handleCoverUpload(file);
                  }}
                />
              </label>
            )}
          </div>
          <div className="flex max-w-44 items-center gap-2">
            {url && (
              <>
                <label className="relative cursor-pointer rounded text-xs font-medium text-accent hover:underline focus-within:ring-2 focus-within:ring-accent/30">
                  <span>{t("uploadCover")}</span>
                  <input
                    type="file"
                    accept="image/jpeg,image/png,image/webp"
                    className="absolute inset-0 h-full w-full cursor-pointer opacity-0"
                    aria-label={t("uploadCover")}
                    disabled={uploadingCover}
                    onChange={(event) => {
                      const file = event.target.files?.[0];
                      if (file) handleCoverUpload(file);
                    }}
                  />
                </label>
                <button
                  type="button"
                  className="ml-auto text-xs text-muted hover:text-foreground"
                  onClick={handleCoverRemove}
                  disabled={uploadingCover}
                >
                  {t("removeCover")}
                </button>
              </>
            )}
          </div>
          {coverError && (
            <p role="alert" className="max-w-44 text-xs leading-5 text-red-700 dark:text-red-300">
              {coverError}
            </p>
          )}
          {uploadingCover && (
            <p role="status" className="max-w-44 text-xs leading-5 text-muted">
              {tw("coverUploading")}
            </p>
          )}
        </div>
      );
    }

    if (field.type === "tags") {
      return (
        <TagInput
          key={field.key}
          className={layoutClass}
          label={label}
          values={normalizeTagValues(value)}
          onChange={(tags) => updateField(field.key, tags)}
          getRemoveAriaLabel={(tag) => tw("removeTag", { tag })}
          placeholder={tw("tagPlaceholder")}
          limitReachedText={tw("tagLimitReached")}
          maxItems={5}
        />
      );
    }

    if (field.type === "textarea") {
      return (
        <div key={field.key} className={`${layoutClass} grid content-start gap-2`}>
          <label htmlFor={inputId} className="text-sm font-medium leading-5 text-muted">
            {label}
          </label>
          <AutoResizeTextarea
            id={inputId}
            value={String(value ?? "")}
            onChange={(nextValue) => updateField(field.key, nextValue)}
            placeholder={tw("fieldPlaceholder", { field: label })}
            minHeight={field.minHeight}
            maxHeight={field.maxHeight}
            ariaDescribedBy={field.recommendedMaxLength !== undefined ? supportId : undefined}
            className={field.key === "plot" ? "text-[15px] leading-7" : "leading-6"}
          />
          {renderCharacterCount(field, value, supportId)}
        </div>
      );
    }

    if (field.type === "number") {
      const numberValue =
        typeof value === "number" && Number.isFinite(value) ? value : undefined;
      const invalidNumber = !isValidOptionalPositiveInteger(value);
      const step = field.key === "words_per_chapter" ? 100 : 1;
      const unit = field.unitKey ? tw(`units.${field.unitKey}`) : "";

      const changeNumberBy = (direction: -1 | 1) => {
        // 空值首次递增时从合理的最小步长开始，递减始终不低于 1。
        const currentValue = isPositiveInteger(numberValue) ? numberValue : 0;
        const nextValue = Math.max(1, currentValue + direction * step);
        updateField(field.key, nextValue);
      };

      return (
        <div key={field.key} className={`${layoutClass} grid content-start gap-2`}>
          <label htmlFor={inputId} className="text-sm font-medium leading-5 text-muted">
            {label}
          </label>
          <div className="flex min-h-12 items-stretch overflow-hidden rounded-xl border border-border bg-background/80 focus-within:border-accent focus-within:ring-2 focus-within:ring-accent/15">
            <button
              type="button"
              className="w-11 shrink-0 border-r border-border text-lg text-muted transition-colors hover:bg-surface-secondary hover:text-foreground disabled:opacity-35"
              onClick={() => changeNumberBy(-1)}
              disabled={numberValue === undefined || numberValue <= 1}
              aria-label={tw("decreaseField", { field: label })}
            >
              −
            </button>
            <input
              id={inputId}
              type="number"
              className="min-w-0 flex-1 bg-transparent px-3 text-center text-base font-semibold tabular-nums text-foreground outline-none"
              value={numberValue ?? ""}
              onChange={(event) => {
                const rawValue = event.target.value;
                // 创建草稿用 undefined 表示未填写；编辑已有小说时用 null 显式清空数据库字段。
                updateField(
                  field.key,
                  rawValue === "" ? (isCreateMode ? undefined : null) : Number(rawValue),
                );
              }}
              min={1}
              step={step}
              aria-invalid={invalidNumber}
              aria-describedby={invalidNumber ? `${inputId}-error` : undefined}
            />
            <span className="grid min-w-16 place-items-center border-l border-border px-3 text-xs text-muted">
              {unit}
            </span>
            <button
              type="button"
              className="w-11 shrink-0 border-l border-border text-lg text-muted transition-colors hover:bg-surface-secondary hover:text-foreground"
              onClick={() => changeNumberBy(1)}
              aria-label={tw("increaseField", { field: label })}
            >
              +
            </button>
          </div>
          {invalidNumber && (
            <p id={`${inputId}-error`} role="alert" className="text-xs leading-5 text-red-700 dark:text-red-300">
              {tw("positiveIntegerRequired")}
            </p>
          )}
        </div>
      );
    }

    if (field.type === "select" && field.options) {
      const stringValue = String(value ?? "");
      const knownValue = field.options.some((option) => option.value === stringValue);
      const options = [
        { value: "", labelKey: "" },
        ...(!knownValue && stringValue ? [{ value: stringValue, labelKey: "" }] : []),
        ...field.options,
      ];

      return (
        <fieldset key={field.key} className={`${layoutClass} grid content-start gap-2`}>
          <legend className="text-sm font-medium leading-5 text-muted">{label}</legend>
          <div className="flex flex-wrap gap-2" role="radiogroup" aria-label={label}>
            {options.map((option) => {
              const selected = option.value === stringValue;
              const optionLabel = !option.value
                ? tw("notSet")
                : option.labelKey
                ? t(option.labelKey)
                : tw("customPov", { value: option.value });
              return (
                <label
                  key={option.value}
                  className={`cursor-pointer rounded-full border px-4 py-2 text-sm font-medium transition-[border-color,background-color,color,box-shadow] focus-within:ring-2 focus-within:ring-accent/20 ${
                    selected
                      ? "border-accent bg-accent text-accent-foreground shadow-sm"
                      : "border-border bg-background/70 text-muted hover:border-accent/50 hover:text-foreground"
                  }`}
                >
                  <input
                    type="radio"
                    name={`${fieldIdPrefix}-${field.key}`}
                    value={option.value}
                    checked={selected}
                    onChange={() => updateField(field.key, option.value)}
                    className="sr-only"
                  />
                  {optionLabel}
                </label>
              );
            })}
          </div>
        </fieldset>
      );
    }

    return (
      <div key={field.key} className={`${layoutClass} grid content-start gap-2`}>
        <label htmlFor={inputId} className="text-sm font-medium leading-5 text-muted">
          {label}
        </label>
        <input
          id={inputId}
          className={`${CONTROL_CLASS} ${
            field.key === "title" ? "py-3 text-lg font-semibold tracking-tight" : ""
          }`}
          value={String(value ?? "")}
          onChange={(event) => updateField(field.key, event.target.value)}
          placeholder={tw("fieldPlaceholder", { field: label })}
          aria-describedby={field.recommendedMaxLength !== undefined ? supportId : undefined}
        />
        {renderCharacterCount(field, value, supportId)}
      </div>
    );
  };

  const sectionTitle = tw(`sections.${sectionKey}`);
  const showEditButton = !isCreateMode && !isEditing;
  const showSaveCancel = !isCreateMode && isEditing;
  const hasInvalidNumberFields = fields.some(
    (field) => field.type === "number" && !isValidOptionalPositiveInteger(getValue(field.key)),
  );
  const renderField = (isEditing || isCreateMode) ? renderEditField : renderReadField;
  const plotField = fields.find((field) => field.key === "plot");
  const coreIdeaField = fields.find((field) => field.key === "core_idea");
  const toneField = fields.find((field) => field.key === "tone");
  const targetAudienceField = fields.find((field) => field.key === "target_audience");

  // 创意设定采用独立左右列，避免主线展开后的高度参与右侧字段的网格行计算。
  const useCreativeColumns =
    sectionKey === "creative" &&
    plotField !== undefined &&
    coreIdeaField !== undefined &&
    toneField !== undefined &&
    targetAudienceField !== undefined;

  return (
    <section className={`grid @[1080px]/novel-info:grid-cols-[10rem_minmax(0,1fr)] @[1080px]/novel-info:gap-x-8 ${isEditing || isCreateMode ? "gap-6 border-t border-border/70 py-8 first:border-t-0 @[1080px]/novel-info:gap-y-8 @[1080px]/novel-info:py-9" : "mt-4 gap-y-4 last:mb-4"}`}>
      <header className="self-start @[1080px]/novel-info:sticky @[1080px]/novel-info:top-0">
        <div className="mb-3 flex items-center gap-3">
          <span className="font-mono text-[15px] font-bold leading-none tracking-[0.16em] text-accent">
            {SECTION_NUMBER[sectionKey]}
          </span>
          <span className="h-px flex-1 bg-border/70" />
        </div>
        <div className="flex flex-wrap items-center gap-1">
          <h3 className="text-lg font-semibold tracking-tight text-foreground">{sectionTitle}</h3>
          {showEditButton && (
            <SectionEditButton label={tw("editSection")} onPress={startEdit} isDisabled={editLocked} />
          )}
        </div>
        <div className={showSaveCancel ? "mt-3 flex flex-wrap items-center gap-2" : "hidden"}>
          {showSaveCancel && (
            <>
              <Button
                variant="ghost"
                size="sm"
                onPress={cancelEdit}
                isDisabled={saving || confirmingDanger || uploadingCover}
              >
                {tw("cancelEdit")}
              </Button>
              <Button
                variant="primary"
                size="sm"
                onPress={saveSection}
                isDisabled={saving || confirmingDanger || uploadingCover || hasInvalidNumberFields}
                className="bg-accent text-accent-foreground hover:bg-accent-hover"
              >
                {saving ? tw("saving") : tw("saveSection")}
              </Button>
            </>
          )}
        </div>

        {saveError && (
          <p role="alert" className="mt-4 border-l-2 border-red-500 pl-3 text-xs leading-5 text-red-700 dark:text-red-300">
            {tw("saveErrorMessage", { error: saveError })}
          </p>
        )}
      </header>

      <div className={`${FIELD_GRID_CLASS} ${isEditing || isCreateMode ? "gap-y-7" : "gap-y-4"}`}>
        {useCreativeColumns ? (
          <>
            {renderField(plotField, "min-w-0 @[900px]/novel-info:col-span-8")}
            <div className={`grid min-w-0 content-start @[900px]/novel-info:col-span-4 ${isEditing || isCreateMode ? "gap-7" : "gap-4"}`}>
              {renderField(coreIdeaField, "min-w-0")}
              <div className={`detail-fields grid min-w-0 content-start ${isEditing || isCreateMode ? "gap-6" : "gap-4"}`}>
                {renderField(toneField, "min-w-0")}
                {renderField(targetAudienceField, "min-w-0")}
              </div>
            </div>
          </>
        ) : (
          fields.map((field) => renderField(field))
        )}
      </div>
    </section>
  );
}
