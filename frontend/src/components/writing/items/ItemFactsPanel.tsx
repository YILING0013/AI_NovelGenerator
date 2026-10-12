"use client";

import { useContext, useEffect, useState } from "react";
import { Button } from "@heroui/react";
import { useTranslations } from "next-intl";
import { RetainedViewActive } from "@/components/layout/RetainedViews";
import { apiGet, apiPost } from "@/lib/api";
import type { ItemReadV1 } from "@/types/item";
import type { HierarchyRecord } from "@/types/hierarchy";
import type { CharacterFactPositionV1 } from "@/types/characterFacts";
import type { ItemFactOperation, ItemFactReadResultV1, ItemFactRecordV1 } from "@/types/itemFacts";
import CharacterFactPositionPicker from "../characters/CharacterFactPositionPicker";
import EvidencePicker from "../foreshadowings/EvidencePicker";
import ItemFactValues, { type ItemFactChoices } from "./ItemFactValues";
import type { ItemFactPreparationV1 } from "./itemFactPreparation";

/** 功能：在物品详情按章前章后查看整组状态和来源。Args: 当前身份、真实目录和原宿主准备回调。Returns: 详情内连续内容。 */
export default function ItemFactsPanel({ novelId, item, chapters, choices, disabled, refresh = 0, onPrepare }: {
  novelId: string; item: ItemReadV1; chapters: HierarchyRecord[]; choices: ItemFactChoices; disabled: boolean;
  refresh?: number;
  onPrepare: (draft: ItemFactPreparationV1) => Promise<void>;
}) {
  const t = useTranslations("writing.characterFacts");
  const f = useTranslations("writing.itemFacts");
  const active = useContext(RetainedViewActive);
  const [position, setPosition] = useState<CharacterFactPositionV1 | null>(null);
  const [retry, setRetry] = useState(0);
  const readKey = JSON.stringify([novelId, item.item_id, item.version, position, retry, refresh]);
  const [read, setRead] = useState<{ key: string; result: ItemFactReadResultV1 | null; history: ItemFactRecordV1[]; more: boolean; error: string }>({ key: "", result: null, history: [], more: false, error: "" });
  const [paging, setPaging] = useState(false);
  // 位置、版本或显式刷新一变就隐藏旧结果，不能在新读取完成前继续按旧状态操作。
  const currentRead = read.key === readKey;
  const result = currentRead ? read.result : null;
  const history = currentRead ? read.history : [];
  const more = currentRead && read.more;
  const loading = !currentRead || paging;
  const error = currentRead ? read.error : "";
  const fact = result?.items.find((row) => row.item_id === item.item_id);
  const initialRecord = history.find((row) => row.position.intent === "book_start" && row.validity.state === "active");
  useEffect(() => {
    if (!active) return;
    const abort = new AbortController();
    void apiPost<ItemFactReadResultV1>(`/api/item-facts/novel/${novelId}/read`, { item_ids: [item.item_id], position }, { signal: abort.signal }).then(async (response) => {
      if (abort.signal.aborted) return;
      if (response.novel_id !== novelId || response.items.some((row) => row.item_id !== item.item_id)) throw new Error(f("wrongScope"));
      const identity = response.read.identities.find((row) => row.item_id === item.item_id);
      const rows = identity ? await apiGet<ItemFactRecordV1[]>(`/api/item-facts/novel/${novelId}/history?entity_id=${identity.entity_id}&limit=100`, { signal: abort.signal }) : [];
      if (rows.some((row) => row.entity_id !== identity?.entity_id || row.item_id !== item.item_id || row.novel_id !== novelId)) throw new Error(f("wrongScope"));
      if (!abort.signal.aborted) setRead({ key: readKey, result: response, history: rows, more: rows.length === 100, error: "" });
    }).catch((failure) => { if (!abort.signal.aborted) setRead({ key: readKey, result: null, history: [], more: false, error: failure.message }); });
    return () => abort.abort();
  }, [active, novelId, item.item_id, position, readKey, f]);
  const prepare = async (operation: ItemFactOperation, record?: ItemFactRecordV1) => {
    if (!fact) return;
    try { await onPrepare({ key: crypto.randomUUID(), revision: 1, novelId, operation, kind: record?.kind ?? (operation === "change" ? "change" : "start"),
      target: { entity_id: fact.entity_id, item_id: item.item_id, expected_version: fact.version, name: item.name },
      position: operation === "correct_initial" ? { version: 1, intent: "book_start", target_type: "novel", target_id: novelId } : record?.position ?? (operation === "change" && position?.target_type === "chapter" ? { ...position, intent: "chapter_after" } : position),
      note: "", evidence: record?.source.kind === "chapter" ? record.source.evidence : null, after: record?.after ?? fact.values ?? { lifecycle_status: "available", owner_character_id: null, controlling_faction_id: null, current_location_id: null }, reason: "", record, resolves: [],
    }); } catch (failure) { setRead((old) => ({ ...old, error: (failure as Error).message })); }
  };
  return <div className="min-w-0 space-y-5" data-testid="item-facts-panel">
    <CharacterFactPositionPicker novelId={novelId} chapters={chapters} value={position} onChange={setPosition} latest disabled={loading} />
    {loading && <p role="status" className="text-sm text-muted">{t("loading")}</p>}
    {error && <div role="alert" className="space-y-2 text-sm text-red-600 dark:text-red-300"><p>{error}</p><Button size="sm" variant="outline" onPress={() => setRetry((value) => value + 1)}>{t("retryRead")}</Button></div>}
    {fact && <><ItemFactValues value={fact.values} choices={choices} />{fact.unknown && <p className="text-sm text-amber-700 dark:text-amber-300">{f(`unknownReasons.${fact.unknown}`)}</p>}
      {!item.is_deleted && <div className="flex flex-wrap gap-2">{(["establish", "change", ...(fact.claimed ? ["correct_initial"] : [])] as ItemFactOperation[]).map((operation) => <Button key={operation} size="sm" variant="outline" isDisabled={disabled || loading || Boolean(error)} onPress={() => void prepare(operation, operation === "correct_initial" ? initialRecord : undefined)}>{f(`operations.${operation}`)}</Button>)}</div>}
      {!fact.claimed && <details><summary className="min-h-11 cursor-pointer py-2 text-sm text-muted">{f("legacy")}</summary><ItemFactValues value={item} choices={choices} /></details>}
    </>}
    {history.length > 0 && <details><summary className="min-h-11 cursor-pointer py-2 text-sm text-accent">{f("history")}</summary><ol className="divide-y divide-border">{history.map((record) => <li key={record.history_id} className="min-w-0 space-y-3 py-4">
      <p className="text-sm">{chapters.find((row) => row.chapter_id === record.position.target_id)?.title} · {t(`positions.${record.position.intent}`)} · {t(`validityStates.${record.validity.state}`)}</p>
      <ItemFactValues value={record.after} choices={choices} />
      {record.source.kind === "author" ? <p className="reading-copy whitespace-pre-wrap">{record.source.note}</p> : <EvidencePicker novelId={novelId} chapters={chapters} value={record.source.evidence} readOnly label={t("source")} />}
      {fact && !item.is_deleted && record.validity.state === "active" && <div className="flex flex-wrap gap-2"><Button size="sm" variant="outline" isDisabled={disabled || loading} onPress={() => void prepare("replace", record)}>{f("operations.replace")}</Button><Button size="sm" variant="ghost" isDisabled={disabled || loading} onPress={() => void prepare("void", record)}>{f("operations.void")}</Button></div>}
    </li>)}</ol>{more && <Button variant="outline" size="sm" isDisabled={loading} onPress={() => {
      setPaging(true);
      void apiGet<ItemFactRecordV1[]>(`/api/item-facts/novel/${novelId}/history?entity_id=${history[0].entity_id}&limit=100&before_version=${history.at(-1)!.after_version}`).then((rows) => { if (rows.some((row) => row.item_id !== item.item_id || row.entity_id !== history[0].entity_id || row.novel_id !== novelId)) throw new Error(f("wrongScope")); setRead((old) => old.key === readKey ? { ...old, history: [...old.history, ...rows], more: rows.length === 100 } : old); }).catch((failure) => setRead((old) => old.key === readKey ? { ...old, error: failure.message } : old)).finally(() => setPaging(false));
    }}>{f("more")}</Button>}</details>}
  </div>;
}
