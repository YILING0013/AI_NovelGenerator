"""Trich xuat / ap dung / kiem tra ban dich tieng Viet cho THONG DIEP LOI + MO TA TRUONG trong backend.

    python tools/i18n_errors.py extract     # thong ke so luong chuoi can dich
    python tools/i18n_errors.py pending     # .err-work/sources_pending.json (nguyen van, khong trung)
    python tools/i18n_errors.py batches N   # chia N lo .err-work/batchNN.json: [{source, kind, files}]
    python tools/i18n_errors.py collect     # gop out_batch*.json -> .err-work/map.json (source->target)
    python tools/i18n_errors.py apply       # ghi ban dich vao file nguon theo nguon-nguyen-van
    python tools/i18n_errors.py check       # chuoi chua chu Han con lai

Boi canh DUOC dich:
  * so dau tien goi ham/lop co ten ket thuc "error"/"Error" (DomainApiError, ValueError, _item_error...)
  * keyword: description=, examples=, detail=, message=, help=, fallback_message=, reason=
  * phan van ban thuong ben trong f-string (giu nguyen bieu thuc {})

Tu choi dich (bao ve dinh danh ky thuat): docstring, khoa dict, ve phai phep so sanh,
tham so re.*, phan tu tuple/set/list (enum), hang so UPPER_CASE, chuoi chua \\ ^ $,
va moi chuoi CHUA mot noi dung bi so sanh o file khac (coupled text).
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / ".err-work"

CJK = re.compile(r"[㐀-䶿一-鿿豈-﫿]")
TECH = re.compile(r"[\\^$]")
SCAN_DIRS = ["backend"]
TEXT_KWARGS = {"description", "examples", "detail", "message", "help", "fallback_message", "reason"}
RE_FUNCS = {"compile", "search", "match", "fullmatch", "sub", "subn", "findall", "split", "finditer"}


def has_cjk(value) -> bool:
    return isinstance(value, str) and bool(CJK.search(value))


def byte_line_starts(raw: bytes):
    starts, pos = [0], 0
    while True:
        idx = raw.find(b"\n", pos)
        if idx == -1:
            break
        pos = idx + 1
        starts.append(pos)
    return starts


def callee_name(func) -> str:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""


def file_segments(path: Path):
    """[{kind, start, end, source, fstring, line}] cua mot file Python."""
    raw = path.read_bytes()
    try:
        tree = ast.parse(raw.decode("utf-8"))
    except Exception:  # noqa: BLE001
        return []
    starts = byte_line_starts(raw)

    docstrings: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", [])
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                docstrings.add(id(body[0].value))

    protected: set[int] = set()

    def protect(*nodes):
        for node in nodes:
            if node is None:
                continue
            for sub in ast.walk(node):
                if isinstance(sub, ast.Constant):
                    protected.add(id(sub))

    for node in ast.walk(tree):
        if isinstance(node, ast.Compare):
            for side in [node.left, *node.comparators]:
                protect(side)
        elif isinstance(node, ast.Dict):
            for key in node.keys:
                if isinstance(key, ast.Constant):
                    protected.add(id(key))
        elif isinstance(node, ast.Call) and callee_name(node.func) in RE_FUNCS:
            for arg in [*node.args, *(kw.value for kw in node.keywords)]:
                protect(arg)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            names = [t.id for t in getattr(node, "targets", [getattr(node, "target", None)]) if isinstance(t, ast.Name)]
            values = [node.value] if node.value is not None else []
            for value in values:
                if isinstance(value, (ast.Tuple, ast.List, ast.Set)):
                    protect(value)
                if any(isinstance(n, str) and n.isupper() and len(n) > 2 for n in names):
                    protect(value)

    found: dict[int, str] = {}

    def add(node, kind: str):
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            return
        if id(node) in protected or id(node) in docstrings or id(node) in found:
            return
        if has_cjk(node.value) and not TECH.search(node.value):
            found[id(node)] = kind

    # f-string dang ky TRUOC: ast.walk theo chieu rong nen node Call den truoc
    # JoinedStr con cua no; neu khong thu tu nay thi manh f-string bi coi la chuoi thuong
    # va bi ghi them dau nhay -> hong cu phap.
    for node in ast.walk(tree):
        if isinstance(node, ast.JoinedStr):
            for value in node.values:
                add(value, "fstring_part")

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = callee_name(node.func)
            if name.endswith("error") or name.endswith("Error"):
                for arg in node.args:
                    for sub in ast.walk(arg):
                        add(sub, "exc_arg")
            for kw in node.keywords or []:
                if kw.arg in TEXT_KWARGS:
                    for sub in ast.walk(kw.value):
                        add(sub, f"kw:{kw.arg}")

    constants = {id(n): n for n in ast.walk(tree) if isinstance(n, ast.Constant)}
    segments = []
    seen_spans = set()
    for node_id, kind in found.items():
        node = constants[node_id]
        start = starts[node.lineno - 1] + node.col_offset
        end = starts[node.end_lineno - 1] + node.end_col_offset
        if (start, end) in seen_spans:
            continue
        seen_spans.add((start, end))
        segments.append({
            "kind": kind,
            "start": start,
            "end": end,
            "source": node.value,
            "fstring": kind == "fstring_part",
            "line": node.lineno,
        })
    segments.sort(key=lambda s: (s["start"], s["end"]))
    return segments


def all_segments():
    rows = []
    for rel_dir in SCAN_DIRS:
        for path in sorted(p for p in (ROOT / rel_dir).rglob("*.py") if ".venv" not in p.parts):
            rel = path.relative_to(ROOT).as_posix()
            for seg in file_segments(path):
                seg["file"] = rel
                rows.append(seg)
    return rows


def coupled_texts():
    """Tap chuoi bi doi khop text o noi khac -> khong duoc dich (se lam hong dieu kien)."""
    texts = set()
    for rel_dir in SCAN_DIRS:
        for path in sorted(p for p in (ROOT / rel_dir).rglob("*.py") if ".venv" not in p.parts):
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Compare):
                    sides = [node.left, *node.comparators]
                    for side in sides:
                        for sub in ast.walk(side):
                            if isinstance(sub, ast.Constant) and has_cjk(sub.value) and len(sub.value) >= 3:
                                texts.add(sub.value)
                if isinstance(node, ast.Dict):
                    for key in node.keys:
                        if isinstance(key, ast.Constant) and has_cjk(key.value):
                            texts.add(key.value)
    return texts


def read_map():
    mapping: dict[str, str] = {}
    files = [WORK / "map.json", WORK / "map_manual.json"]
    for f in files:
        if f.exists():
            for row in json.loads(f.read_text(encoding="utf-8")):
                mapping[row["source"]] = row["target"]
    return mapping


def sanitize(target: str, *, fstring: bool) -> str:
    """Bo bao dau nhay / escape do model copy theo dinh dang source cu."""
    if fstring:
        return target
    value = re.sub(r'"\s*\r?\n\s*"', "\n", target)
    changed = True
    while changed and len(value) >= 2:
        changed = False
        if value[0] == '"' and value[-1] == '"':
            value = value[1:-1]
            changed = True
        elif value.startswith('\\"') and value.endswith('\\"'):
            value = value[2:-2]
            changed = True
    return value.replace('\\"', '"').replace("\\\\n", "\n").replace("\\n", "\n").replace("\\t", "\t")


def cmd_extract() -> int:
    rows = all_segments()
    coupled = coupled_texts()
    kept = [r for r in rows if not any(c in r["source"] for c in coupled)]
    kinds: dict[str, int] = defaultdict(int)
    for r in kept:
        kinds[r["kind"]] += len(r["source"])
    print(f"chuoi_dich_duoc={len(kept)} ky_tu={sum(len(r['source']) for r in kept)} files={len({r['file'] for r in kept})}")
    for kind, chars in sorted(kinds.items(), key=lambda kv: -kv[1]):
        print(f"   {chars:>6}  {kind}")
    print(f"   bi chan (coupled/ky thuat) = {len(rows) - len(kept)}")
    return 0


def cmd_pending() -> int:
    mapping = read_map()
    coupled = coupled_texts()
    seen: dict[str, dict] = {}
    for r in all_segments():
        if any(c in r["source"] for c in coupled) or r["source"] in mapping:
            continue
        item = seen.setdefault(r["source"], {"source": r["source"], "kind": r["kind"], "files": []})
        if len(item["files"]) < 3:
            item["files"].append(f"{r['file']}:{r['line']}")
    rows = sorted(seen.values(), key=lambda x: -len(x["source"]))
    (WORK / "sources_pending.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"unique_sources_thieu={len(rows)} ky_tu={sum(len(r['source']) for r in rows)}")
    return 0


def cmd_batches(count: int) -> int:
    rows = json.loads((WORK / "sources_pending.json").read_text(encoding="utf-8"))
    half = (len(rows) + count - 1) // count
    for i in range(count):
        chunk = rows[i * half:(i + 1) * half]
        (WORK / f"batch{i:02d}.json").write_text(json.dumps(chunk, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"batch{i:02d}: items={len(chunk)} chars={sum(len(x['source']) for x in chunk)}")
    return 0


def cmd_collect() -> int:
    """Gop toan bo out_batch*.json (source->target) vao map.json, trung lap = loi."""
    merged: dict[str, str] = {}
    conflicts = 0
    rows_out = []
    for f in sorted(WORK.glob("out_batch*.json")):
        for row in json.loads(f.read_text(encoding="utf-8")):
            source, target = row.get("source"), row.get("target")
            if not source or not target:
                continue
            if source in merged and merged[source] != target:
                conflicts += 1
                continue
            if source not in merged:
                merged[source] = target
                rows_out.append({"source": source, "target": target})
    (WORK / "map.json").write_text(json.dumps(rows_out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"map.json={len(rows_out)} entries, mau thuan={conflicts}")
    return 0


def cmd_apply() -> int:
    mapping = read_map()
    coupled = coupled_texts()
    files: dict[str, list] = defaultdict(list)
    cache: dict[str, bytes] = {}
    skipped = rejected = partial = 0
    for r in all_segments():
        if any(c in r["source"] for c in coupled):
            continue
        raw_target = mapping.get(r["source"])
        if raw_target is None:
            skipped += 1
            continue
        target = sanitize(raw_target, fstring=r["fstring"])
        if not target.strip():
            rejected += 1
            continue
        if r["file"] not in cache:
            cache[r["file"]] = (ROOT / r["file"]).read_bytes()
        slice_text = cache[r["file"]][r["start"]:r["end"]].decode("utf-8")
        quoted = slice_text[:1] in {'"', "'", "f", "F", "r", "R", "b", "B"}
        if quoted:
            # Chi an toan neu slice la MOT literal hoan chinh (mo dau va dong dau bang nhau).
            # Truong hop noat lien "abc" f"def{{x}}" bi gop thanh node dau tien co span
            # che qua dau nhay + tien to f -> khong the thay bang toan block, bo qua.
            closes = slice_text[-1:] in {'"', "'"}
            opens_same = slice_text[:1].rstrip("fFrRbB") == slice_text[-1:] or (
                slice_text[:1] in {'"', "'"} and slice_text[-1:] == slice_text[:1]
            )
            if not (closes and opens_same and len(slice_text) >= 2):
                partial += 1
                continue
            literal = json.dumps(target, ensure_ascii=False).encode("utf-8")
        else:
            # Manh ben trong f-string: chi an toan khi slice la van ban thuan
            # (khong chua dau nhay, backslash hay newline - nguoc lai span cua ast
            # da che qua ranh gioi gitua cac literal duoc noi ham).
            if '"' in slice_text or "'" in slice_text or "\\" in slice_text or "\n" in slice_text:
                partial += 1
                continue
            if '"' in target or "\\" in target:
                rejected += 1
                continue
            literal = target.replace("{", "{{").replace("}", "}}").encode("utf-8")
        files[r["file"]].append((r["start"], r["end"], literal))
    for rel, edits in files.items():
        path = ROOT / rel
        raw = cache[rel]
        for start, end, literal in sorted(edits, key=lambda e: -e[0]):
            raw = raw[:start] + literal + raw[end:]
        path.write_bytes(raw)
    print(f"files={len(files)} edits={sum(len(v) for v in files.values())} chua_dich={skipped} bi_tu_cho={rejected} bo_qua_manh_cat_ngang_dong={partial}")
    return 0


def cmd_check() -> int:
    rows = all_segments()
    bad_lines = []
    for r in rows:
        bad_lines.append((r["file"], r["line"], r["kind"], r["source"][:120]))
    print(f"segments_con_chu_Han={len(bad_lines)} ky_tu={sum(len(r['source']) for r in rows)}")
    for row in bad_lines[:20]:
        print("   ", *row)
    return 0


COMMANDS = {"extract": cmd_extract, "pending": cmd_pending, "collect": cmd_collect, "apply": cmd_apply, "check": cmd_check}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("cmd", nargs="?", default="check", choices=[*COMMANDS, "batches"])
    parser.add_argument("n", nargs="?", default=5, type=int)
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass
    WORK.mkdir(exist_ok=True)
    args = parser.parse_args()
    if args.cmd == "batches":
        return cmd_batches(args.n)
    return COMMANDS[args.cmd]()


if __name__ == "__main__":
    sys.exit(main())
