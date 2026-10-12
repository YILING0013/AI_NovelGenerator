"use client";

import { useEffect, useState, type RefObject } from "react";
import { Button } from "@heroui/react";
import { useTranslations } from "next-intl";
import ReadOnlyField from "@/components/shared/ReadOnlyField";
import { RelationEditorErrorSummary } from "@/components/shared/RelationEditorPrimitives";
import type { CharacterFactField } from "@/types/characterFacts";
import type { CharacterVolumeStateReadV1 } from "@/types/characterVolumeState";

const FIELDS = ["psychological_state", "public_state", "hidden_state"] as const;
type Field = typeof FIELDS[number];
export type CharacterLegacyVolumeUpdate = Partial<Pick<CharacterVolumeStateReadV1, Field>> & { expected_version: number };
const LABELS = { psychological_state: "psychologicalState", public_state: "publicState", hidden_state: "hiddenState" };

/** 功能：原业务节内管理尚未认领的旧文字；受管字段永久只读。Args: 旧状态原版本、共享读取的认领名单及窄写/当前读回。Returns: 非权威旧文字编辑区。 */
export default function CharacterLegacyVolumeFields({ state, claimedFields, disabled = false, onSave, onReadback, onBusy, beforeLeaveRef }: {
  state: CharacterVolumeStateReadV1; claimedFields?: CharacterFactField[]; disabled?: boolean;
  onBusy?: (busy: boolean) => void; beforeLeaveRef?: RefObject<(() => Promise<void>) | null>;
  onSave: (patch: CharacterLegacyVolumeUpdate) => Promise<void>; onReadback: () => Promise<void>;
}) {
  const t = useTranslations("writing.characterVolumeStates"), ft = useTranslations("writing.characterFacts");
  const [draft, setDraft] = useState<{ original: CharacterVolumeStateReadV1; values: Pick<CharacterVolumeStateReadV1, Field>; fields: Field[]; saved: boolean } | null>(null);
  const [busy, setBusy] = useState(false), [error, setError] = useState("");
  useEffect(() => { onBusy?.(busy); return () => onBusy?.(false); }, [busy, onBusy]);
  useEffect(() => {
    if (!beforeLeaveRef) return;
    beforeLeaveRef.current = async () => { if (busy || draft) throw new Error(ft("finishLegacyEditing")); };
    return () => { beforeLeaveRef.current = null; };
  }, [beforeLeaveRef, busy, draft, ft]);
  const available = claimedFields === undefined ? [] : FIELDS.filter((field) => !claimedFields.includes(field));
  const save = async () => {
    if (!draft || busy || disabled) return;
    const patch: CharacterLegacyVolumeUpdate = { expected_version: draft.original.version };
    for (const field of draft.fields) if (draft.values[field] !== draft.original[field]) patch[field] = draft.values[field];
    if (!draft.saved && Object.keys(patch).length === 1) { setDraft(null); return; }
    if (!draft.saved && FIELDS.some((field) => Object.hasOwn(patch, field) && !available.includes(field))) { setError(ft("managedLegacyField")); return; }
    setBusy(true); setError("");
    try {
      if (!draft.saved) { await onSave(patch); setDraft({ ...draft, saved: true }); }
      await onReadback(); setDraft(null);
    } catch (failure) { setError((failure as Error).message); }
    finally { setBusy(false); }
  };
  return <div className="space-y-4">
    <p className="text-xs text-muted">{ft("legacyEditingNote")}</p>
    {error && <RelationEditorErrorSummary message={error} />}
    <dl className="detail-fields grid gap-4">{FIELDS.map((field) => draft?.fields.includes(field)
      ? <label key={field} className="grid gap-2 text-xs font-medium text-muted">{t(`fields.${LABELS[field]}`)}<textarea name={field} className="min-h-28 rounded-xl border border-border bg-background px-3 py-2 text-sm text-foreground" value={draft.values[field]} disabled={disabled || busy || draft.saved} maxLength={1000} onChange={(event) => setDraft({ ...draft, values: { ...draft.values, [field]: event.target.value } })} /></label>
      : <ReadOnlyField key={field} label={t(`fields.${LABELS[field]}`)} value={state[field] || ft("cleared")} wide />)}</dl>
    {draft ? <div className="flex gap-2"><Button size="sm" variant="primary" isDisabled={disabled || busy} onPress={() => void save()}>{ft(draft.saved ? "retryRead" : "saveLegacyText")}</Button><Button size="sm" variant="ghost" isDisabled={disabled || busy || draft.saved} onPress={() => { setDraft(null); setError(""); }}>{ft("close")}</Button></div>
      : available.length > 0 && <Button size="sm" variant="ghost" isDisabled={disabled || busy} onPress={() => { setDraft({ original: structuredClone(state), values: { psychological_state: state.psychological_state, public_state: state.public_state, hidden_state: state.hidden_state }, fields: [...available], saved: false }); setError(""); }}>{ft("editLegacyText")}</Button>}
  </div>;
}
