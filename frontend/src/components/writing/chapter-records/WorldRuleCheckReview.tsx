"use client";

import { Button } from "@heroui/react";
import { useContext, useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { RetainedViewActive } from "@/components/layout/RetainedViews";
import { RelationEditorErrorSummary } from "@/components/shared/RelationEditorPrimitives";
import { apiGet } from "@/lib/api";
import type { WorldRuleReadV1 } from "@/types/worldRule";
import type { ChapterCheckedWorldRuleV1 } from "@/types/chapterRecords";
import { FORESHADOWING_INPUT as INPUT } from "../foreshadowings/EvidencePicker";
import type { ChapterWorldRulesCheck } from "./chapterRecordDrafts";

/** 功能：检查前后都完整显示固定规则，不截断例外或后果。Args: rules 本次完整快照。Returns: 连续规则正文。 */
function RuleSnapshots({ rules }: { rules: Array<WorldRuleReadV1 | ChapterCheckedWorldRuleV1> }) {
  const t = useTranslations("writing.chapterRecords.worldRuleCheck");
  const ruleT = useTranslations("writing.worldRules");
  return <div className="grid min-w-0 gap-4">{rules.map((rule) => <section key={rule.rule_id} data-testid="world-rule-snapshot" className="grid min-w-0 gap-3 border-t border-border pt-3">
    <h5 className="break-words text-sm font-semibold">{t("ruleVersion", { name: rule.name, version: rule.version })}</h5>
    <dl className="detail-fields grid min-w-0 gap-4 text-sm">
      <div><dt className="text-xs text-muted">{t("ruleId")}</dt><dd className="break-all font-mono">{rule.rule_id}</dd></div>
      {"entity_id" in rule && <div><dt className="text-xs text-muted">{t("entityId")}</dt><dd className="break-all font-mono">{rule.entity_id}</dd></div>}
      <div><dt className="text-xs text-muted">{t("novelId")}</dt><dd className="break-all font-mono">{rule.novel_id}</dd></div>
      <div><dt className="text-xs text-muted">{ruleT("fields.category")}</dt><dd>{rule.category}</dd></div>
      <div><dt className="text-xs text-muted">{ruleT("fields.scopeType")}</dt><dd>{ruleT(`scope.${rule.scope_type}`)}</dd></div>
      <div><dt className="text-xs text-muted">{t("scopeIds")}</dt><dd className="break-all">{rule.scope_entity_ids.join(" / ") || t("emptyValue")}</dd></div>
      <div><dt className="text-xs text-muted">{ruleT("fields.status")}</dt><dd>{ruleT(`status.${rule.status}`)}</dd></div>
      <div><dt className="text-xs text-muted">{ruleT("fields.priority")}</dt><dd className="tabular-nums">{rule.priority}</dd></div>
      <div><dt className="text-xs text-muted">{ruleT("fields.order")}</dt><dd className="tabular-nums">{rule.order_index}</dd></div>
      <div><dt className="text-xs text-muted">{t("deleted")}</dt><dd>{t(rule.is_deleted ? "yes" : "no")}</dd></div>
      <div className="col-span-full"><dt className="text-xs text-muted">{ruleT("fields.tags")}</dt><dd className="reading-copy whitespace-pre-wrap">{rule.tags.join(" / ") || t("emptyValue")}</dd></div>
      <div className="col-span-full"><dt className="text-xs text-muted">{ruleT("fields.statement")}</dt><dd className="reading-copy whitespace-pre-wrap">{rule.statement}</dd></div>
      <div className="col-span-full"><dt className="text-xs text-muted">{ruleT("fields.enforcement")}</dt><dd className="reading-copy whitespace-pre-wrap">{rule.enforcement || t("emptyValue")}</dd></div>
    </dl>
    <div><h6 className="text-xs text-muted">{ruleT("sections.exceptions")}</h6>{rule.exceptions.length ? <ul className="grid gap-2">{rule.exceptions.map((exception, index) => <li key={index} className="grid gap-1"><p className="reading-copy whitespace-pre-wrap">{ruleT("fields.exceptionCondition")}: {exception.condition}</p><p className="reading-copy whitespace-pre-wrap">{ruleT("fields.exceptionEffect")}: {exception.effect}</p></li>)}</ul> : <p className="text-sm text-muted">{ruleT("empty.noExceptions")}</p>}</div>
    <div><h6 className="text-xs text-muted">{ruleT("sections.consequences")}</h6>{rule.costs_and_consequences.length ? <ul className="list-inside list-disc">{rule.costs_and_consequences.map((cost, index) => <li key={index} className="reading-copy whitespace-pre-wrap">{cost}</li>)}</ul> : <p className="text-sm text-muted">{ruleT("empty.noConsequences")}</p>}</div>
  </section>)}</div>;
}

/** 功能：只供作者选择本书一至五条活动全局规则，刷新不替换已选版本。Args: props 原稿选择与更新回调。Returns: 规则选择和完整开始快照。 */
export function WorldRuleSelection({ novelId, rules, disabled, onChange }: { novelId: string; rules: WorldRuleReadV1[]; disabled: boolean; onChange: (rules: WorldRuleReadV1[]) => void }) {
  const t = useTranslations("writing.chapterRecords.worldRuleCheck");
  const active = useContext(RetainedViewActive);
  const [rows, setRows] = useState<WorldRuleReadV1[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [refresh, setRefresh] = useState(0);
  useEffect(() => {
    if (!active || disabled) return;
    const abort = new AbortController();
    void apiGet<WorldRuleReadV1[]>(`/api/world-rules/novel/${novelId}`, { signal: abort.signal }).then((data) => {
      if (!abort.signal.aborted) { setRows(data.filter((rule) => rule.novel_id === novelId && !rule.is_deleted && rule.status === "active" && rule.scope_type === "global")); setError(""); }
    }).catch((failure) => { if (!abort.signal.aborted) setError(failure.message); }).finally(() => { if (!abort.signal.aborted) setLoading(false); });
    return () => abort.abort();
  }, [novelId, active, refresh, disabled]);
  return <section aria-label={t("selectRules")} className="grid min-w-0 gap-3 border-t border-border pt-4">
    <div className="flex flex-wrap items-center justify-between gap-2"><h4 className="text-sm font-semibold">{t("selectRules")}</h4><Button variant="ghost" size="sm" isDisabled={disabled || loading} onPress={() => { setLoading(true); setError(""); setRefresh((value) => value + 1); }}>{t("refreshRules")}</Button></div>
    {loading && !disabled && <p role="status" className="text-sm">{t("loadingRules")}</p>}
    {error && <RelationEditorErrorSummary message={error} />}
    {!loading && !error && !rows.length && <p role="status" className="text-sm">{t("noRules")}</p>}
    <fieldset className="grid gap-1"><legend className="sr-only">{t("selectRules")}</legend>{[...rows, ...rules.filter((rule) => !rows.some((row) => row.rule_id === rule.rule_id))].map((rule) => {
      const selected = rules.find((item) => item.rule_id === rule.rule_id);
      return <label key={rule.rule_id} className="flex min-h-11 items-start gap-2 text-sm"><input type="checkbox" className="mt-1" disabled={disabled || loading || Boolean(error) || !selected && rules.length >= 5} checked={Boolean(selected)} onChange={() => onChange(selected ? rules.filter((item) => item.rule_id !== rule.rule_id) : [...rules, rule])} /><span className="min-w-0 break-words">{t("ruleVersion", { name: (selected ?? rule).name, version: (selected ?? rule).version })}</span></label>;
    })}</fieldset>
    {rules.length > 0 && <><h4 className="text-xs font-medium text-muted">{t("selectedSnapshots")}</h4><RuleSnapshots rules={rules} /></>}
  </section>;
}

/** 功能：逐条审阅疑点，只有明确追加才把文字交给原报告。Args: props 原检查及审阅回调。Returns: 疑点、逐条引文和实际规则快照。 */
export function WorldRuleCheckResult({ check, blocked, inputsMatch, onCheck, onAdopt }: { check: ChapterWorldRulesCheck; blocked: boolean; inputsMatch: boolean; onCheck: (check: ChapterWorldRulesCheck) => Promise<unknown>; onAdopt: (check: ChapterWorldRulesCheck) => void }) {
  const t = useTranslations("writing.chapterRecords.worldRuleCheck");
  if (!check.result) return null;
  const result = check.result;
  const edits = check.issueEdits ?? result.candidate.issues.map((issue) => ({ text: issue.text, selected: false, rejected: false, appended: false }));
  const selected = edits.filter((edit) => edit.selected && !edit.rejected && !edit.appended);
  const valid = selected.every((edit) => { const length = Array.from(edit.text.trim()).length; return length >= 1 && length <= 2000; });
  const update = (index: number, change: Partial<typeof edits[number]>) => { void onCheck({ ...check, issueEdits: edits.map((edit, position) => position === index ? { ...edit, ...change } : edit) }).catch(() => {}); };
  return <div data-testid="world-rules-check-result" className="grid min-w-0 gap-4">
    <p className="border-l-2 border-amber-500 px-3 text-sm">{t("reviewRisk")}</p>
    <div className="break-all text-xs text-muted"><p>{t("checkedSource", { chapter: check.source.chapter_id, version: check.source.version })}</p><p>{t("revisionId")}: {check.source.revision_id}</p><p>{t("contentHash")}: {check.source.content_hash}</p></div>
    {result.candidate.issues.length === 0 ? <p role="status" className="text-sm">{t("noIssues")}</p> : <ul className="grid min-w-0 gap-4">{result.candidate.issues.map((issue, index) => {
      const edit = edits[index];
      return <li key={index} className="grid min-w-0 gap-2 border-t border-border pt-3">
        <label className="flex min-h-11 items-center gap-2 text-sm"><input type="checkbox" checked={edit.selected} disabled={blocked || edit.rejected || edit.appended} onChange={(event) => update(index, { selected: event.target.checked })} />{t("selectIssue", { index: index + 1 })}</label>
        <label className="grid min-w-0 gap-1 text-xs text-muted">{t("issueText", { index: index + 1 })}<textarea className={`${INPUT} min-h-28`} value={edit.text} disabled={blocked || edit.rejected || edit.appended} onChange={(event) => update(index, { text: event.target.value })} /></label>
        {edit.text !== issue.text && <div><h5 className="text-xs text-muted">{t("originalIssue")}</h5><p className="reading-copy whitespace-pre-wrap">{issue.text}</p></div>}
        <div><h5 className="text-xs text-muted">{t("quote", { start: issue.start })}</h5><p className="reading-copy whitespace-pre-wrap">{issue.quote}</p></div>
        <ul className="text-xs text-muted">{issue.rule_ids.map((id) => { const rule = result.checked_rules.find((row) => row.rule_id === id)!; return <li key={id} className="break-words">{t("ruleVersion", { name: rule.name, version: rule.version })} · {id}</li>; })}</ul>
        {edit.rejected || edit.appended ? <p role="status" className="text-sm">{t(edit.rejected ? "rejected" : edit.duplicate ? "duplicateIssue" : "appended")}</p> : <Button variant="ghost" className="justify-self-start" isDisabled={blocked} onPress={() => update(index, { selected: false, rejected: true })}>{t("rejectIssue", { index: index + 1 })}</Button>}
      </li>;
    })}</ul>}
    {!valid && <p role="alert" className="text-sm text-danger">{t("issueLength")}</p>}
    {result.candidate.issues.length > 0 && <Button variant="outline" className="justify-self-start" isDisabled={blocked || !inputsMatch || !selected.length || !valid} onPress={() => onAdopt(check)}>{t("append")}</Button>}
    <p className="border-l-2 border-amber-500 px-3 text-sm">{t("reportBoundary")}</p>
    <h4 className="text-sm font-semibold">{t("checkedSnapshots")}</h4><RuleSnapshots rules={result.checked_rules} />
  </div>;
}
