"use client";

import { TooltipHint } from "@/components/shared/TooltipHint";
import type { JsonSchema } from "@/types/taskFlow";
import {
  defaultKeymap,
  history,
  historyKeymap,
  isolateHistory,
} from "@codemirror/commands";
import { json } from "@codemirror/lang-json";
import {
  bracketMatching,
  HighlightStyle,
  syntaxHighlighting,
} from "@codemirror/language";
import { linter, type Diagnostic } from "@codemirror/lint";
import {
  Compartment,
  EditorState,
  Transaction,
  type Extension,
} from "@codemirror/state";
import {
  Decoration,
  EditorView,
  keymap,
  lineNumbers,
  MatchDecorator,
  ViewPlugin,
  WidgetType,
  type ViewUpdate,
} from "@codemirror/view";
import { Button } from "@heroui/react";
import { tags } from "@lezer/highlight";
import { useTranslations } from "next-intl";
import { useEffect, useId, useMemo, useRef, useState } from "react";

const EMPTY_PORTS: Record<string, JsonSchema> = {};
const PORT_PATTERN = /(?<!\{)\{([A-Za-z_][A-Za-z0-9_]*)\}(?!\})/g;
const INVALID_EDITOR =
  "[data-flow-json-editor='true'][aria-invalid='true'], textarea:not([data-flow-preview-field='true'])[aria-invalid='true']";
const EDITOR_THEME = EditorView.theme({
  "&": {
    color: "var(--foreground)",
    backgroundColor: "var(--surface)",
    border: "1px solid var(--border)",
    borderRadius: "10px",
    fontSize: "13px",
    overflow: "hidden",
  },
  "&.cm-focused": { outline: "2px solid var(--accent)", outlineOffset: "1px" },
  ".cm-content": {
    padding: "10px 0",
    minHeight: "112px",
    caretColor: "var(--accent)",
  },
  ".cm-scroller": {
    fontFamily: "var(--app-font-mono)",
    lineHeight: "1.8",
    overflow: "auto",
    maxHeight: "360px",
    overscrollBehavior: "contain",
    scrollbarWidth: "thin",
    scrollbarColor: "var(--border) transparent",
  },
  ".cm-line": { padding: "0 10px" },
  ".cm-gutters": {
    backgroundColor: "var(--surface-secondary)",
    color: "var(--muted)",
    borderRight: "1px solid var(--border)",
  },
  ".cm-activeLineGutter": { backgroundColor: "var(--color-selected)" },
  ".cm-cursor, .cm-dropCursor": { borderLeftColor: "var(--accent)" },
  ".cm-selectionBackground, &.cm-focused .cm-selectionBackground, ::selection":
    { backgroundColor: "var(--color-selected) !important" },
  ".cm-tooltip": {
    backgroundColor: "var(--color-surface-raised)",
    color: "var(--foreground)",
    border: "1px solid var(--border)",
  },
  ".cm-panels": {
    backgroundColor: "var(--surface-secondary)",
    color: "var(--foreground)",
  },
  ".cm-diagnostic": { borderLeftColor: "var(--danger)", padding: "4px 8px" },
  ".cm-flow-port": {
    display: "inline-block",
    padding: "0 6px",
    margin: "0 1px",
    border: "1px solid var(--accent)",
    borderRadius: "999px",
    backgroundColor: "var(--color-selected)",
    color: "var(--foreground)",
    fontFamily: "var(--app-font-sans)",
    fontSize: "12px",
    lineHeight: "1.6",
    verticalAlign: "baseline",
  },
  ".cm-flow-unknown": {
    textDecoration: "underline wavy var(--danger)",
    textUnderlineOffset: "3px",
  },
});
const JSON_HIGHLIGHT = syntaxHighlighting(
  HighlightStyle.define([
    { tag: tags.propertyName, color: "var(--accent)", fontWeight: "600" },
    { tag: tags.string, color: "var(--foreground)" },
    { tag: [tags.number, tags.bool, tags.null], color: "var(--accent)" },
    { tag: tags.punctuation, color: "var(--muted)" },
  ]),
);

/** 功能：读取真正会被后端替换的输入名称。Args: text 提示词。Returns: 不重复的输入名称。 */
export function flowPromptInputs(text: string): string[] {
  return [
    ...new Set([...text.matchAll(PORT_PATTERN)].map((match) => match[1])),
  ];
}

class InputPortWidget extends WidgetType {
  constructor(
    readonly name: string,
    readonly label: string,
  ) {
    super();
  }
  eq(other: InputPortWidget) {
    return this.name === other.name && this.label === other.label;
  }
  toDOM() {
    const element = document.createElement("span");
    element.className = "cm-flow-port";
    element.textContent = this.label;
    element.setAttribute("aria-label", `{${this.name}}`);
    element.setAttribute("title", `{${this.name}}`);
    element.dataset.inputPort = this.name;
    return element;
  }
  ignoreEvent() {
    return false;
  }
}

function inputPortTags(
  ports: Record<string, JsonSchema>,
): Extension {
  const matcher = new MatchDecorator({
    regexp: PORT_PATTERN,
    decoration: (match) =>
      ports[match[1]]
        ? Decoration.replace({
            widget: new InputPortWidget(
              match[1],
              String(ports[match[1]].title || match[1]),
            ),
          })
        : Decoration.mark({ class: "cm-flow-unknown" }),
  });
  return ViewPlugin.fromClass(
    class {
      decorations;
      constructor(view: EditorView) {
        this.decorations = matcher.createDeco(view);
      }
      update(update: ViewUpdate) {
        this.decorations = matcher.updateDeco(update, this.decorations);
      }
    },
    {
      decorations: (value) => value.decorations,
      provide: (plugin) =>
        EditorView.atomicRanges.of(
          (view) => view.plugin(plugin)?.decorations || Decoration.none,
        ),
    },
  );
}

type CodeSurfaceProps = {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  extensions: Extension;
  viewRef: React.RefObject<EditorView | null>;
  invalid?: boolean;
  jsonField?: boolean;
  equivalentJson?: boolean;
};

// CodeMirror 自己保存光标、组合输入和撤销记录；React 回传相同内容时不重建编辑器。
function CodeSurface({
  id,
  label,
  value,
  onChange,
  extensions,
  viewRef,
  invalid,
  jsonField,
  equivalentJson,
}: CodeSurfaceProps) {
  const host = useRef<HTMLDivElement>(null);
  const latest = useRef({ onChange, value, label, id });
  const [configuration] = useState(() => new Compartment());
  useEffect(() => {
    latest.current = { onChange, value, label, id };
  }, [onChange, value, label, id]);
  useEffect(() => {
    const view = new EditorView({
      parent: host.current!,
      state: EditorState.create({
        doc: latest.current.value,
        extensions: [
          EDITOR_THEME,
          EditorView.lineWrapping,
          history(),
          keymap.of([...defaultKeymap, ...historyKeymap]),
          configuration.of([]),
          EditorView.contentAttributes.of({
            id: latest.current.id,
            "aria-label": latest.current.label,
            "aria-multiline": "true",
            spellcheck: "false",
          }),
          EditorView.updateListener.of((update) => {
            if (
              update.docChanged &&
              !update.transactions.every(
                (transaction) =>
                  transaction.annotation(Transaction.addToHistory) === false,
              )
            ) {
              latest.current.onChange(update.state.doc.toString());
            }
          }),
        ],
      }),
    });
    viewRef.current = view;
    return () => {
      view.destroy();
      viewRef.current = null;
    };
  }, [configuration, viewRef]);
  useEffect(() => {
    viewRef.current?.dispatch({
      effects: configuration.reconfigure(extensions),
    });
  }, [configuration, extensions, viewRef]);
  useEffect(() => {
    const view = viewRef.current;
    if (!view) return;
    const current = view.state.doc.toString();
    if (current === value) return;
    if (equivalentJson) {
      try {
        if (
          JSON.stringify(JSON.parse(current)) ===
          JSON.stringify(JSON.parse(value))
        )
          return;
      } catch {
        /* 未写完的 JSON 只在父级实际换值时覆盖。 */
      }
    }
    // 外部撤销或切换版本只替换不同的片段，保留其余选区和滚动位置。
    let from = 0;
    while (
      from < current.length &&
      from < value.length &&
      current[from] === value[from]
    )
      from += 1;
    let oldEnd = current.length,
      newEnd = value.length;
    while (
      oldEnd > from &&
      newEnd > from &&
      current[oldEnd - 1] === value[newEnd - 1]
    ) {
      oldEnd -= 1;
      newEnd -= 1;
    }
    view.dispatch({
      changes: { from, to: oldEnd, insert: value.slice(from, newEnd) },
      annotations: Transaction.addToHistory.of(false),
    });
  }, [value, equivalentJson, viewRef]);
  useEffect(() => {
    const content = viewRef.current?.contentDOM;
    if (!content) return;
    content.setAttribute("aria-label", label);
    if (jsonField) content.setAttribute("data-flow-json-editor", "true");
    if (invalid) {
      content.setAttribute("aria-invalid", "true");
      content.setAttribute("aria-describedby", `${id}-error`);
    } else {
      content.removeAttribute("aria-invalid");
      content.removeAttribute("aria-describedby");
    }
  }, [id, invalid, jsonField, label, viewRef]);
  return <div ref={host} className="min-w-0" />;
}

type PromptEditorProps = {
  label: string;
  value: string;
  onChange: (value: string) => void;
  ports: Record<string, JsonSchema>;
  requiredPorts?: string[];
  relatedPrompts?: string[];
  formatInputs?: boolean;
  help?: string;
};

/** 功能：在提示词内用标签显示输入，并检查漏填和未知输入。Args: props 提示词、可选输入及更新回调。Returns: 保持原字符串的提示词编辑器。 */
export function FlowPromptEditor({
  label,
  value,
  onChange,
  ports,
  requiredPorts = [],
  relatedPrompts = [],
  formatInputs = true,
  help,
}: PromptEditorProps) {
  const t = useTranslations("taskFlows");
  const id = useId();
  const viewRef = useRef<EditorView | null>(null);
  const extensions = useMemo(
    () => (formatInputs ? inputPortTags(ports) : []),
    [ports, formatInputs],
  );
  const referenced = flowPromptInputs(value);
  const known = new Set([
    ...referenced,
    ...relatedPrompts.flatMap(flowPromptInputs),
  ]);
  const unknown = referenced.filter((name) => !(name in ports));
  const missing = requiredPorts.filter((name) => !known.has(name));
  const unsupported = [
    ...value.matchAll(
      /(?<!\{)\{([A-Za-z_][A-Za-z0-9_]*)([.\[:!][^{}]*)\}(?!\})/g,
    ),
  ].map((match) => match[0]);
  return (
    <div className="grid min-w-0 gap-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <label htmlFor={id} className="text-xs font-medium text-muted">
          {label}
        </label>
        <TooltipHint
          text={
            help ||
            t(
              formatInputs
                ? "codeEditors.promptHelp"
                : "codeEditors.literalPromptHelp",
            )
          }
        />
      </div>
      {formatInputs && Object.keys(ports).length > 0 && (
        <select
          aria-label={t("codeEditors.insertInput")}
          className="min-h-11 w-full min-w-0 rounded-xl border border-border bg-surface-secondary px-3 text-xs text-foreground focus-visible:outline-2 focus-visible:outline-accent"
          value=""
          onChange={(event) => {
            const view = viewRef.current;
            if (!view || !event.target.value) return;
            const text = `{${event.target.value}}`;
            view.dispatch(view.state.replaceSelection(text), {
              scrollIntoView: true,
              userEvent: "input",
              annotations: isolateHistory.of("full"),
            });
            view.focus();
          }}
        >
          <option value="">{t("codeEditors.insertInput")}</option>
          {Object.entries(ports).map(([name, schema]) => (
            <option key={name} value={name}>
              {schema.title ? `${schema.title} · ${name}` : name}
            </option>
          ))}
        </select>
      )}
      <CodeSurface
        id={id}
        label={label}
        value={value}
        onChange={onChange}
        extensions={extensions}
        viewRef={viewRef}
      />
      {unknown.length > 0 && (
        <p role="alert" className="text-xs text-danger">
          {t("codeEditors.unknownInputs", { names: unknown.join(", ") })}
        </p>
      )}
      {unsupported.length > 0 && (
        <p role="alert" className="text-xs text-danger">
          {t("codeEditors.unsupportedInputs", {
            names: unsupported.join(", "),
          })}
        </p>
      )}
      {!formatInputs && referenced.length > 0 && (
        <p role="status" className="text-xs text-muted">
          {t("codeEditors.literalInputs", { names: referenced.join(", ") })}
        </p>
      )}
      {missing.length > 0 && (
        <p role="status" className="text-xs text-muted">
          {t("codeEditors.missingInputs", { names: missing.join(", ") })}
        </p>
      )}
    </div>
  );
}

type JsonExample = {
  from: number;
  to: number;
  source: string;
};

// 未加引号的输入会在运行时变成 JSON 值；校对用临时值，格式化后恢复原占位符。
function prepareJsonExample(
  example: JsonExample,
  ports: Record<string, JsonSchema>,
  formatSuffix: boolean,
  formatting = false,
) {
  if (!formatSuffix)
    return {
      normalized: example.source,
      replacements: [] as [string, string][],
    };
  const source = example.source;
  const matches = new Map(
    [...source.matchAll(PORT_PATTERN)]
      .filter((match) => match[1] in ports)
      .map((match) => [match.index, match]),
  );
  let prefix = "__flow_json_input_";
  while (source.includes(prefix)) prefix += "_";
  let quoted = false,
    escaped = false,
    normalized = "";
  const replacements: [string, string][] = [];
  for (let index = 0; index < source.length; index += 1) {
    const char = source[index];
    const match = !quoted && matches.get(index);
    if (match) {
      const marker = JSON.stringify(`${prefix}${replacements.length}`);
      normalized += formatting ? marker : '"x"'.padEnd(match[0].length, " ");
      replacements.push([marker, match[0]]);
      index += match[0].length - 1;
      continue;
    }
    if (quoted) {
      if (escaped) escaped = false;
      else if (char === "\\") escaped = true;
      else if (char === '"') quoted = false;
    } else if (char === '"') quoted = true;
    normalized += char;
  }
  return {
    normalized,
    replacements,
  };
}

/** 功能：定位输出指令里的 JSON 示例，保留前后文字。Args: text 完整后缀。Returns: JSON 原始片段及位置；纯指令返回 null。 */
export function readFlowJsonExample(text: string): JsonExample | null {
  const fenced = /```(?:json)?[ \t]*\r?\n([\s\S]*?)(?:```|$)/i.exec(text);
  let from: number, to: number;
  if (fenced) {
    from = fenced.index + fenced[0].indexOf("\n") + 1;
    to = from + fenced[1].length;
  } else {
    const start = /(?:^|\n)[ \t]*([\[{])|[\[{](?=[ \t]*["{\[])/m.exec(text);
    if (!start) return null;
    from = start.index + start[0].search(/[\[{]/);
    to = text.length;
    let depth = 0,
      quoted = false,
      escaped = false;
    for (let index = from; index < text.length; index += 1) {
      const char = text[index];
      if (quoted) {
        if (escaped) escaped = false;
        else if (char === "\\") escaped = true;
        else if (char === '"') quoted = false;
      } else if (char === '"') quoted = true;
      else if (char === "{" || char === "[") {
        depth += 1;
      } else if (char === "}" || char === "]") {
        depth -= 1;
        if (depth === 0) {
          to = index + 1;
          break;
        }
      }
    }
  }
  const source = text.slice(from, to);
  return {
    from,
    to,
    source,
  };
}

function jsonDiagnostic(
  text: string,
  message: string,
  offset = 0,
): Diagnostic[] {
  try {
    JSON.parse(text);
    return [];
  } catch (error) {
    const match = /position (\d+)/.exec(
      error instanceof Error ? error.message : "",
    );
    const position = match ? Number(match[1]) : Math.max(0, text.length - 1);
    return [
      {
        from: offset + position,
        to: offset + Math.min(text.length, position + 1),
        severity: "error",
        message,
      },
    ];
  }
}

// 所有 JSON 字段共享保存边界；一个字段修好不能掩盖另一个字段的错误。
function reportJsonValidity(
  view: EditorView | null,
  valid: boolean,
  callback?: (valid: boolean) => void,
) {
  if (view) {
    view.contentDOM.dataset.flowJsonEditor = "true";
    if (valid) view.contentDOM.removeAttribute("aria-invalid");
    else view.contentDOM.setAttribute("aria-invalid", "true");
  }
  callback?.(!document.querySelector(INVALID_EDITOR));
}

type JsonEditorProps = {
  label: string;
  value: unknown;
  onChange: (value: unknown) => void;
  onValidityChange?: (valid: boolean) => void;
  help?: string;
  validationScope?: "definition" | "preview";
};

/** 功能：编辑带行号、校对和格式化的 JSON，错误时保留草稿。Args: props 当前值及有效值回调。Returns: JSON 编辑字段。 */
export function FlowJsonEditor({
  label,
  value,
  onChange,
  onValidityChange,
  help,
  validationScope = "definition",
}: JsonEditorProps) {
  const t = useTranslations("taskFlows");
  const id = useId();
  const viewRef = useRef<EditorView | null>(null);
  const validityRef = useRef(onValidityChange);
  const serialized = JSON.stringify(value ?? null, null, 2);
  const [failure, setFailure] = useState({ baseline: serialized, message: "" });
  const error = failure.baseline === serialized ? failure.message : "";
  useEffect(() => {
    validityRef.current = onValidityChange;
  }, [onValidityChange]);
  useEffect(() => {
    // 临时示例的错误只影响模拟，不阻断方案保存。
    if (validationScope === "preview") validityRef.current?.(!error);
    else reportJsonValidity(viewRef.current, !error, validityRef.current);
  }, [error, validationScope]);
  useEffect(
    () => () => {
      if (validationScope === "definition")
        queueMicrotask(() =>
          validityRef.current?.(!document.querySelector(INVALID_EDITOR)),
        );
    },
    [validationScope],
  );
  const extensions = useMemo(
    () => [
      lineNumbers(),
      json(),
      JSON_HIGHLIGHT,
      bracketMatching(),
      linter(
        (view) => jsonDiagnostic(view.state.doc.toString(), t("invalidJson")),
        { delay: 200 },
      ),
    ],
    [t],
  );
  return (
    <div className="grid min-w-0 gap-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <label htmlFor={id} className="text-xs font-medium text-muted">
            {label}
          </label>
          <TooltipHint text={help || t("codeEditors.jsonHelp")} />
        </div>
        <Button
          size="sm"
          variant="ghost"
          isDisabled={!!error}
          onPress={() => {
            const view = viewRef.current;
            if (view)
              view.dispatch({
                changes: {
                  from: 0,
                  to: view.state.doc.length,
                  insert: JSON.stringify(
                    JSON.parse(view.state.doc.toString()),
                    null,
                    2,
                  ),
                },
                userEvent: "input",
                annotations: isolateHistory.of("full"),
              });
            view?.focus();
          }}
        >
          {t("codeEditors.formatJson")}
        </Button>
      </div>
      <CodeSurface
        id={id}
        label={label}
        value={serialized}
        extensions={extensions}
        viewRef={viewRef}
        invalid={!!error}
        jsonField={validationScope === "definition"}
        equivalentJson
        onChange={(text) => {
          try {
            const next: unknown = JSON.parse(text);
            onChange(next);
            setFailure({ baseline: serialized, message: "" });
            if (validationScope === "preview") onValidityChange?.(true);
            else reportJsonValidity(viewRef.current, true, onValidityChange);
          } catch (failure) {
            setFailure({
              baseline: serialized,
              message:
                failure instanceof Error && !(failure instanceof SyntaxError)
                  ? failure.message
                  : t("invalidJson"),
            });
            if (validationScope === "preview") onValidityChange?.(false);
            else reportJsonValidity(viewRef.current, false, onValidityChange);
          }
        }}
      />
      {error && (
        <p id={`${id}-error`} role="alert" className="text-xs text-danger">
          {error}
        </p>
      )}
    </div>
  );
}

type SuffixEditorProps = {
  label: string;
  value: string;
  onChange: (value: string) => void;
  onValidityChange?: (valid: boolean) => void;
  ports?: Record<string, JsonSchema>;
  formatSuffix?: boolean;
  help?: string;
};

/** 功能：校对输出后缀中的 JSON 示例，同时保留前后指令。Args: props 完整后缀及更新回调。Returns: JSON 后缀编辑器。 */
export function FlowJsonSuffixEditor({
  label,
  value,
  onChange,
  onValidityChange,
  ports = EMPTY_PORTS,
  formatSuffix = false,
  help,
}: SuffixEditorProps) {
  const t = useTranslations("taskFlows");
  const id = useId();
  const viewRef = useRef<EditorView | null>(null);
  const validityRef = useRef(onValidityChange);
  const example = readFlowJsonExample(value);
  const diagnostic = example
    ? jsonDiagnostic(
        prepareJsonExample(example, ports, formatSuffix)
          .normalized,
        t("invalidJson"),
        example.from,
      )
    : [];
  const error = diagnostic[0]?.message || "";
  const unknown = formatSuffix
    ? flowPromptInputs(value).filter((name) => !(name in ports))
    : [];
  useEffect(() => {
    validityRef.current = onValidityChange;
  }, [onValidityChange]);
  useEffect(() => {
    reportJsonValidity(viewRef.current, !error, validityRef.current);
  }, [error]);
  useEffect(
    () => () => {
      queueMicrotask(() =>
        validityRef.current?.(!document.querySelector(INVALID_EDITOR)),
      );
    },
    [],
  );
  const extensions = useMemo(
    () => [
      lineNumbers(),
      json(),
      JSON_HIGHLIGHT,
      bracketMatching(),
      ...(formatSuffix ? [inputPortTags(ports)] : []),
      linter(
        (view) => {
          const part = readFlowJsonExample(view.state.doc.toString());
          return part
            ? jsonDiagnostic(
                prepareJsonExample(part, ports, formatSuffix)
                  .normalized,
                t("invalidJson"),
                part.from,
              )
            : [];
        },
        { delay: 200 },
      ),
    ],
    [formatSuffix, ports, t],
  );
  return (
    <div className="grid min-w-0 gap-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <label htmlFor={id} className="text-xs font-medium text-muted">
            {label}
          </label>
          <TooltipHint text={help || t("codeEditors.suffixHelp")} />
        </div>
        <Button
          size="sm"
          variant="ghost"
          isDisabled={!example || !!error}
          onPress={() => {
            const view = viewRef.current;
            if (!view) return;
            const part = readFlowJsonExample(view.state.doc.toString());
            if (!part) return;
            const prepared = prepareJsonExample(
              part,
              ports,
              formatSuffix,
              true,
            );
            let formatted = JSON.stringify(
              JSON.parse(prepared.normalized),
              null,
              2,
            );
            for (const [marker, placeholder] of prepared.replacements)
              formatted = formatted.replaceAll(marker, placeholder);
            const leading = /^\s*/.exec(part.source)![0];
            const trailing = /\s*$/.exec(part.source)![0];
            view.dispatch({
              changes: {
                from: part.from,
                to: part.to,
                insert: leading + formatted + trailing,
              },
              userEvent: "input",
              annotations: isolateHistory.of("full"),
            });
            view.focus();
          }}
        >
          {t("codeEditors.formatJson")}
        </Button>
      </div>
      <CodeSurface
        id={id}
        label={label}
        value={value}
        onChange={onChange}
        extensions={extensions}
        viewRef={viewRef}
        invalid={!!error}
        jsonField
      />
      {error && (
        <p id={`${id}-error`} role="alert" className="text-xs text-danger">
          {error}
        </p>
      )}
      {!example && value.trim() && (
        <p role="status" className="text-xs text-muted">
          {t("codeEditors.noJsonExample")}
        </p>
      )}
      {unknown.length > 0 && (
        <p role="alert" className="text-xs text-danger">
          {t("codeEditors.unknownInputs", { names: unknown.join(", ") })}
        </p>
      )}
    </div>
  );
}
