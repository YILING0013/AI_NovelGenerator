"""List CJK string literals that are NEITHER docstrings NOR collected by i18n_errors.

Những chuỗi này là ứng viên "customer/LLM-facing" còn sót lại ngoài tầm codemod.
"""

from __future__ import annotations

import ast
import io
import pathlib
import re
import sys
import tokenize

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from i18n_errors import all_segments  # noqa: E402

CJK = re.compile(r"[\u3400-\u9fff]")


def doc_lines(tree: ast.AST) -> set[int]:
    lines: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", None)
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                lines.update(range(body[0].lineno, body[0].end_lineno + 1))
    return lines


covered = {(r["file"], r["start"]) for r in all_segments()}
rows = []
for p in sorted(pathlib.Path("backend").rglob("*.py")):
    rel = p.as_posix()
    text = p.read_text(encoding="utf-8")
    try:
        tree = ast.parse(text)
    except SyntaxError:
        continue
    docs = doc_lines(tree)
    for tok in tokenize.generate_tokens(io.StringIO(text).readline):
        if tok.type != tokenize.STRING:
            continue
        start_byte = len(text[: tok.start[0] - 1].encode("utf-8")) + len(
            text.splitlines(keepends=True)[tok.start[0] - 1].encode("utf-8")[: tok.start[1]]
        )
        if (rel, start_byte) in covered or tok.start[0] in docs:
            continue
        try:
            value = ast.literal_eval(tok.string)
        except Exception:  # noqa: BLE001
            continue
        if isinstance(value, str) and CJK.search(value) and len(value) >= 3:
            rows.append((len(value), rel, tok.start[0], value[:110]))

rows.sort(reverse=True)
print("ung viên con sot:", len(rows), "ky tu:", sum(r[0] for r in rows))
for n, rel, line, val in rows[:30]:
    print(f"{n:5d} {rel}:{line}  {val!r}")
