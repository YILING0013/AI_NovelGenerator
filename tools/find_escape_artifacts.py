from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

needle = "\\n"  # hai ky tu: \ va n
rows = []
for p in sorted((ROOT / "backend").rglob("*.py")):
    try:
        tree = ast.parse(p.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        print("PARSE FAIL", p, exc)
        continue
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and needle in node.value:
            rows.append((p.relative_to(ROOT).as_posix(), node.lineno, node.end_lineno, node.value[:120]))

print("values containing literal backslash-n:", len(rows))
for r in rows[:40]:
    print(f"{r[0]}:{r[1]}-{r[2]}  {r[3]!r}"[:180])
