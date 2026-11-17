"""Trích xuất / áp dụng / kiểm tra bản tiếng Việt của bộ prompt sinh truyện.

Cách dùng (chạy từ thư mục repo):
    python tools/i18n_prompts.py extract    # sinh .promo-work/units/*.json + manifest.json
    python tools/i18n_prompts.py apply      # nap .promo-work/translated/*.json vào file gốc
    python tools/i18n_prompts.py verify     # kiểm tra placeholder, JSON/PY parse được
    python tools/i18n_prompts.py stats      # đếm segment theo loại

Quy tắc an toàn:
* Chỉ chuỗi có ký tự CJK mới được coi là cần dịch.
* Key JSON nằm trong PROTECTED_KEYS bị bỏ qua: node id/label/name là khóa i18n của frontend,
  dịch chúng sẽ làm hỏng tra cứu giao diện.
* File .md được coi là 1 segment duy nhất (giữ nguyên placeholder {var} và khối JSON mẫu).
"""

from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / ".promo-work"
UNITS = WORK / "units"
TRANS = WORK / "translated"

CJK = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
PLACEHOLDER = re.compile(r"\{[A-Za-z_][A-Za-z0-9_]{0,40}\}|<[a-zA-Z_][a-zA-Z0-9_]{0,40}>|\$\{[A-Za-z_][^}\n]{0,60}\}")
PROTECTED_KEYS = {
    "id", "task", "type", "label", "name", "node_id", "ref", "key",
    "prompt_ref", "provider", "model", "format_version", "revision", "edge_id",
    # "title" la nhan hien thi duoc frontend dich qua inputLabels.*; de nguyen de giu
    # dieu kien so sanh "phai la mac dinh tieng Trung khong" trong TaskFlowForm.
    "title",
}
DEFAULTS_DIR = "backend/services/task_flows/defaults"
SCHEMA_DIR = "backend/llm/schemas"
PROMPT_YAML = "backend/llm/prompts/default/llm_provider_test.yaml"

# Tầng 2: thong diep nguoi dung trong backend (ngoai docstring/comment).
# Loai desktop_launcher vi cac gia tri tieng Trung trong do duoc dung de so sanh (mode == "生产模式").
MESSAGE_PY = [
    "backend/migrations/task_flows.py",
    "backend/api/error_protocol.py",
    "backend/runtime.py",
    "backend/migrations/__init__.py",
    "backend/storage.py",
]


def has_cjk(text) -> bool:
    return isinstance(text, str) and bool(CJK.search(text))


def tokens(text: str) -> list[str]:
    return sorted(set(PLACEHOLDER.findall(text or "")))


def slug(rel: str) -> str:
    return rel.replace("/", "_").replace(":", "_").replace(".", "_")


# ---------------------------------------------------------------- trích xuất
def walk_json(node, path, out):
    if isinstance(node, dict):
        for k, v in node.items():
            if isinstance(v, str) and has_cjk(v) and k not in PROTECTED_KEYS:
                out.append({"path": path + [k], "text": v})
            elif isinstance(v, str):
                continue
            else:
                walk_json(v, path + [k], out)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            if isinstance(v, str):
                if has_cjk(v):
                    out.append({"path": path + [i], "text": v})
            else:
                walk_json(v, path + [i], out)


def py_field_strings(text: str):
    """Lấy chuỗi trong description= / examples= của Field (và hằng UPPER_CASE cấp module)."""
    found = []
    tree = ast.parse(text)

    class Visitor(ast.NodeVisitor):
        def visit_Call(self, node):  # noqa: N802
            for kw in node.keywords or []:
                if kw.arg in {"description", "examples"}:
                    items = kw.value.elts if isinstance(kw.value, (ast.List, ast.Tuple)) else [kw.value]
                    for item in items:
                        if isinstance(item, ast.Constant) and has_cjk(item.value):
                            found.append({
                                "text": item.value,
                                "lineno": item.lineno, "col": item.col_offset,
                                "end_lineno": item.end_lineno, "end_col": item.end_col_offset,
                            })
            self.generic_visit(node)

        def _assign(self, value):
            if isinstance(value, ast.Constant) and has_cjk(value.value):
                found.append({
                    "text": value.value,
                    "lineno": value.lineno, "col": value.col_offset,
                    "end_lineno": value.end_lineno, "end_col": value.end_col_offset,
                })

        def visit_Assign(self, node):  # noqa: N802
            # chi dich hang so UPPER_CASE (prompt/template inside module)
            for target in node.targets:
                names = []
                if isinstance(target, ast.Name):
                    names = [target.id]
                elif isinstance(target, (ast.Tuple, ast.List)):
                    names = [getattr(e, "id", "") for e in target.elts]
                if any(isinstance(n, str) and n.isupper() and len(n) > 2 for n in names):
                    self._assign(node.value)
            self.generic_visit(node)

        def visit_AnnAssign(self, node):  # noqa: N802
            target = node.target
            name = getattr(target, "id", "")
            if isinstance(name, str) and name.isupper() and len(name) > 2:
                self._assign(node.value)
            self.generic_visit(node)

    Visitor().visit(tree)
    seen = set()
    out = []
    for f in found:
        key = (f["lineno"], f["col"])
        if key in seen:
            continue
        seen.add(key)
        out.append(f)
    return out


def yaml_strings(text: str):
    out = []
    pattern = re.compile(r'^([ \t]*)([A-Za-z_][A-Za-z0-9_]*:[ \t]*)(.+?)[ \t]*$', re.M)
    for m in pattern.finditer(text):
        raw = m.group(3)
        if not has_cjk(raw):
            continue
        quote = '"' if raw.startswith('"') else ("'" if raw.startswith("'") else "")
        body = raw[1:-1] if quote and len(raw) > 1 else raw
        out.append({"value_span": (m.start(3) + (1 if quote else 0), m.end(3) - (1 if quote else 0)),
                    "text": body, "quote": quote})
    return out


def collect():
    """Trả về danh sách unit: {id, kind, file, segments[]}."""
    units = []

    for path in sorted((ROOT / DEFAULTS_DIR).glob("*.md")):
        rel = path.relative_to(ROOT).as_posix()
        text = path.read_text(encoding="utf-8")
        if has_cjk(text):
            units.append({"id": f"md::{rel}", "kind": "md", "file": rel,
                          "segments": [{"text": text, "locator": "full"}]})

    for path in sorted((ROOT / DEFAULTS_DIR).glob("*.json")):
        rel = path.relative_to(ROOT).as_posix()
        segs = []
        walk_json(json.loads(path.read_text(encoding="utf-8")), [], segs)
        if segs:
            units.append({"id": f"json::{rel}", "kind": "json", "file": rel,
                          "segments": [{"text": s["text"], "path": s["path"],
                                        "locator": ".".join(str(p) for p in s["path"])} for s in segs]})

    for path in sorted((ROOT / SCHEMA_DIR).glob("*.py")):
        rel = path.relative_to(ROOT).as_posix()
        text = path.read_text(encoding="utf-8")
        segs = py_field_strings(text)
        if segs:
            units.append({"id": f"py::{rel}", "kind": "py", "file": rel,
                          "segments": [dict(s, locator=f"{s['lineno']}:{s['col']}") for s in segs]})

    yaml_path = ROOT / PROMPT_YAML
    if yaml_path.exists():
        rel = yaml_path.relative_to(ROOT).as_posix()
        segs = yaml_strings(yaml_path.read_text(encoding="utf-8"))
        if segs:
            units.append({"id": f"yaml::{rel}", "kind": "yaml", "file": rel,
                          "segments": [dict(s, locator=str(i)) for i, s in enumerate(segs)]})

    for u in units:
        for i, s in enumerate(u["segments"]):
            s["seg"] = i
            s["tokens"] = tokens(s["text"])
    return units


def extract():
    units = collect()
    for old in list(UNITS.glob("*.json")) if UNITS.exists() else []:
        old.unlink()
    UNITS.mkdir(parents=True, exist_ok=True)
    TRANS.mkdir(parents=True, exist_ok=True)
    manifest = []
    for u in units:
        name = slug(u["id"]) + ".json"
        payload = {"id": u["id"], "kind": u["kind"], "file": u["file"],
                   "segments": [{"seg": s["seg"], "locator": s["locator"], "tokens": s["tokens"],
                                 "source": s["text"]} for s in u["segments"]]}
        (UNITS / name).write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
        manifest.append({"id": u["id"], "kind": u["kind"], "file": u["file"], "unit_file": name,
                         "segments": len(u["segments"]), "chars": sum(len(s["text"]) for s in u["segments"])})
    manifest.sort(key=lambda m: -m["chars"])
    (WORK / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"units={len(manifest)} segments={sum(m['segments'] for m in manifest)} chars={sum(m['chars'] for m in manifest)}")


def stats():
    units = collect()
    by_kind = {}
    for u in units:
        by_kind[u["kind"]] = by_kind.get(u["kind"], 0) + len(u["segments"])
    print("units=", len(units), "segments by kind=", by_kind,
          "chars=", sum(len(s["text"]) for u in units for s in u["segments"]))
    for u in sorted(units, key=lambda x: -sum(len(s["text"]) for s in x["segments"]))[:25]:
        print(f"{sum(len(s['text']) for s in u['segments']):>7} {len(u['segments']):>4} {u['id']}")


def read_translations():
    table = {}
    missing_target = []
    if not TRANS.exists():
        return table
    for f in sorted(TRANS.glob("*.json")):
        data = json.loads(f.read_text(encoding="utf-8"))
        for seg in data.get("segments", []):
            if "target" not in seg:
                missing_target.append((data.get("id"), seg.get("seg")))
                continue
            table[(data["id"], seg["seg"])] = seg["target"]
    if missing_target:
        print(f"canh bao: {len(missing_target)} segment chua co target (giu nguyen ban goc)")
    return table


def apply():
    units = collect()
    table = read_translations()
    changed, untouched = 0, []
    for u in units:
        file = ROOT / u["file"]
        got = [(s["seg"], table[(u["id"], s["seg"])]) for s in u["segments"] if (u["id"], s["seg"]) in table]
        if len(got) < len(u["segments"]):
            untouched.append(f"{u['id']} ({len(got)}/{len(u['segments'])})")
        if not got:
            continue
        targets = dict(got)
        text = file.read_text(encoding="utf-8")

        if u["kind"] == "md":
            new = targets[0]
            if not new.endswith("\n"):
                new += "\n"
            file.write_text(new, encoding="utf-8")
            changed += 1
            continue

        if u["kind"] == "json":
            data = json.loads(text)
            for seg in u["segments"]:
                if seg["seg"] not in targets:
                    continue
                cur = data
                for step in seg["path"][:-1]:
                    cur = cur[step]
                cur[seg["path"][-1]] = targets[seg["seg"]]
            file.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            changed += 1
            continue

        if u["kind"] == "py":
            raw = text.encode("utf-8")
            starts = [0]
            pos = 0
            while True:
                idx = raw.find(b"\n", pos)
                if idx == -1:
                    break
                pos = idx + 1
                starts.append(pos)

            def off(lineno, col):
                return starts[min(lineno, len(starts)) - 1] + col

            edits = []
            for seg in u["segments"]:
                if seg["seg"] not in targets:
                    continue
                new = json.dumps(targets[seg["seg"]], ensure_ascii=False).encode("utf-8")
                edits.append((off(seg["lineno"], seg["col"]), off(seg["end_lineno"], seg["end_col"]), new))
            for start, end, literal in sorted(edits, key=lambda e: -e[0]):
                raw = raw[:start] + literal + raw[end:]
            file.write_bytes(raw)
            changed += 1
            continue

        if u["kind"] == "yaml":
            segs = yaml_strings(text)
            for i, seg in sorted(enumerate(segs), key=lambda p: -p[0]):
                if i not in targets:
                    continue
                s, e = seg["value_span"]
                text = text[:s] + json.dumps(targets[i], ensure_ascii=False) + text[e:]
            file.write_text(text, encoding="utf-8")
            changed += 1

    print(f"files updated={changed}")
    for t in untouched:
        print("  thieu ban dich:", t)


def verify():
    problems = []
    units = collect()
    table = read_translations()
    # 1) file nguồn phải parse/compile được
    for u in units:
        file = ROOT / u["file"]
        text = file.read_text(encoding="utf-8")
        if u["kind"] == "json":
            try:
                json.loads(text)
            except Exception as exc:  # noqa: BLE001
                problems.append(f"{u['file']}: JSON {exc}")
        if u["kind"] == "py":
            try:
                ast.parse(text)
            except Exception as exc:  # noqa: BLE001
                problems.append(f"{u['file']}: PY {exc}")
    # 2) chất lượng bản dịch: token, số dòng md, ký tự Hán sót
    for u in units:
        for s in u["segments"]:
            target = table.get((u["id"], s["seg"]))
            if target is None:
                continue
            want = sorted(set(tokens(target)))
            if want != sorted(s["tokens"]):
                problems.append(f"{u['id']} seg{s['seg']}: placeholder {sorted(s['tokens'])} -> {want}")
            if has_cjk(target):
                bad = "".join(sorted(set(CJK.findall(target))))
                problems.append(f"{u['id']} seg{s['seg']}: con {len(bad)} ky tu Han: {bad[:12]}")
            if CJK_EAST_PUNCT.search(target):
                problems.append(f"{u['id']} seg{s['seg']}: con dau cau Trung Hoa")
            if u["kind"] == "md" and target.rstrip("\n").count("\n") != s["text"].rstrip("\n").count("\n"):
                problems.append(
                    f"{u['id']} seg{s['seg']}: so dong doi {s['text'].rstrip(chr(10)).count(chr(10))} -> {target.rstrip(chr(10)).count(chr(10))}"
                )
            if u["kind"] == "md":
                for block in JSON_BLOCKS.findall(target):
                    try:
                        json.loads(block)
                    except Exception:  # noqa: BLE001
                        pass
    missing = [(u["id"], len(u["segments"])) for u in units
               if any((u["id"], s["seg"]) not in table for s in u["segments"])]
    print(f"problems={len(problems)} units_thieu_ban_dich={len(missing)}")
    for p in problems[:60]:
        print("  ", p)
    for m in missing[:20]:
        print("   chua dich:", m[0], f"({m[1]} seg)")


CJK_EAST_PUNCT = re.compile(r"[、：；？！「」『』（）《》〈〉，]")
JSON_BLOCKS = re.compile(r"```json\s*(.*?)```", re.S)


def _segment_text(payload):
    file = ROOT / payload["file"]
    if not file.exists():
        return None
    if payload["kind"] == "md":
        return file.read_text(encoding="utf-8")
    if payload["kind"] == "json":
        data = json.loads(file.read_text(encoding="utf-8"))
        texts = []
        for seg in payload["segments"]:
            cur = data
            ok = True
            for step in seg["locator"].split("."):
                if step.isdigit() and isinstance(cur, list):
                    cur = cur[int(step)]
                elif isinstance(cur, dict) and step in cur:
                    cur = cur[step]
                else:
                    ok = False
                    break
            if ok and isinstance(cur, str):
                texts.append(cur)
        return "\n".join(texts) if texts else None
    if payload["kind"] == "py":
        text = file.read_text(encoding="utf-8")
        try:
            tree = ast.parse(text)
        except Exception:  # noqa: BLE001
            return None
        pool = {s["source"].strip() for s in payload["segments"]}
        found = [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str) and n.value.strip() in pool]
        return "\n".join(found) if found else None
    return None


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass
    cmd = sys.argv[1] if len(sys.argv) > 1 else "stats"
    {"extract": extract, "apply": apply, "verify": verify, "stats": stats}[cmd]()
