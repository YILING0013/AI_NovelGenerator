"""Phan loai chuoi chua chu Han con lai trong backend de quyet dinh pham vi dich.

    python tools/cjk_classify.py [thu_muc...]

Mo tai:
- desc/examples : mo ta truong pydantic -> LLM va UI dung, nen dich
- compare       : gia tri so sanh (dinh danh ky thuat) -> KHONG duoc dich
- dict_key      : key cua dict (identifier) -> KHONG duoc dich
- fstring_part  : manh ben trong f-string -> dich co than trong (giu {expr})
- call:<fn>     : tham so ham (logger/raise/Field/help...) -> xem ten ham
- bare_expr     : chuoi dung minh (thuong la note trong source) -> bo qua
"""

from __future__ import annotations

import ast
import collections
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CJK = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")


def classify(paths):
    buckets = collections.Counter()
    chars = collections.Counter()
    call_names = collections.Counter()
    samples = collections.defaultdict(list)
    for base in paths:
        files = sorted(base.rglob("*.py")) if base.is_dir() else [base]
        for f in files:
            if ".venv" in f.parts:
                continue
            try:
                tree = ast.parse(f.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                continue
            parents = {}
            for node in ast.walk(tree):
                for child in ast.iter_child_nodes(node):
                    parents[id(child)] = node

            docstrings = set()
            for node in ast.walk(tree):
                if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                    body = getattr(node, "body", [])
                    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                        docstrings.add(id(body[0].value))

            kw_value_ids = {}
            compare_ids = set()
            dict_key_ids = set()
            fstring_ids = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.keyword) and node.arg in {"description", "examples", "title", "description_typ"}:
                    for sub in ast.walk(node.value):
                        if isinstance(sub, ast.Constant):
                            kw_value_ids[id(sub)] = node.arg
                if isinstance(node, ast.Compare):
                    for side in [node.left, *node.comparators]:
                        for sub in ast.walk(side):
                            if isinstance(sub, ast.Constant):
                                compare_ids.add(id(sub))
                if isinstance(node, ast.Dict):
                    for key in node.keys:
                        if isinstance(key, ast.Constant):
                            dict_key_ids.add(id(key))
                if isinstance(node, ast.JoinedStr):
                    for value in node.values:
                        if isinstance(value, ast.Constant):
                            fstring_ids.add(id(value))

            for node in ast.walk(tree):
                if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
                    continue
                if id(node) in docstrings or not CJK.search(node.value):
                    continue
                n = len(CJK.findall(node.value))
                if id(node) in kw_value_ids:
                    kind = f"kw:{kw_value_ids[id(node)]}"
                elif id(node) in compare_ids:
                    kind = "compare"
                elif id(node) in dict_key_ids:
                    kind = "dict_key"
                elif id(node) in fstring_ids:
                    kind = "fstring_part"
                else:
                    parent = parents.get(id(node))
                    if isinstance(parent, ast.Call):
                        func = parent.func
                        name = getattr(func, "attr", "") or getattr(func, "id", "")
                        kind = f"call:{name}"
                    elif isinstance(parent, ast.Expr):
                        kind = "bare_expr"
                    else:
                        kind = f"other:{type(parent).__name__}"
                buckets[kind] += 1
                chars[kind] += n
                if len(samples[kind]) < 4:
                    samples[kind].append((f.relative_to(ROOT).as_posix(), node.lineno, node.value[:90]))
                if kind.startswith("call:"):
                    call_names[kind] += n
    return buckets, chars, samples, call_names


def main() -> int:
    args = [Path(a) if Path.is_absolute(Path(a)) else ROOT / a for a in sys.argv[1:]] or [ROOT / "backend"]
    buckets, chars, samples, _ = classify(args)
    total = sum(chars.values())
    print(f"ROOT={args}  tong ky tu Han ngoai chu thich = {total}")
    for kind, count in chars.most_common(26):
        print(f"{count:>7} chu ({buckets[kind]:>5} chuoi)  {kind}")
    print()
    for kind, _count in chars.most_common(12):
        print(f"### {kind}")
        for rel, line, text in samples[kind]:
            print(f"   {rel}:{line}  {text!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
