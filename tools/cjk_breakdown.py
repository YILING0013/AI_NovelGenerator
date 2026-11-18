"""Phân tách ký tự tiếng Trung theo loại: comment / docstring / chuỗi nghiệp vụ.

Dùng tokenize để không nhầm chuỗi trong docstring với comment, và ast để xác định
docstring (module/class/function).
"""

from __future__ import annotations

import ast
import io
import pathlib
import re
import tokenize
from collections import Counter

CJK = re.compile(r"[\u3400-\u9fff]")


def docstring_spans(tree: ast.AST) -> set[tuple[int, int]]:
    spans: set[tuple[int, int]] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", None)
            if not body:
                continue
            first = body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
                spans.add((first.lineno, first.end_lineno))
    return spans


def main() -> int:
    kinds: Counter = Counter()
    for p in sorted(pathlib.Path("backend").rglob("*.py")):
        try:
            text = p.read_text(encoding="utf-8")
            tree = ast.parse(text)
        except Exception:  # noqa: BLE001
            continue
        docs = docstring_spans(tree)
        comment = 0
        literal = 0
        doc = 0
        lines = text.splitlines()
        in_doc = [i + 1 for i in range(len(lines))]
        def is_doc(line: int) -> bool:
            return any(a <= line <= b for a, b in docs)

        for tok in tokenize.generate_tokens(io.StringIO(text).readline):
            if tok.type == tokenize.COMMENT:
                comment += len(CJK.findall(tok.string))
            elif tok.type == tokenize.STRING:
                if is_doc(tok.start[0]):
                    doc += len(CJK.findall(tok.string))
                else:
                    literal += len(CJK.findall(tok.string))
        kinds["comment"] += comment
        kinds["docstring dev"] += doc
        kinds["chuoi nghiep vu"] += literal
    for k, v in kinds.most_common():
        print(f"{v:8d}  {k}")
    print(f"{sum(kinds.values()):8d}  TONG backend/*.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
