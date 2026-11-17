"""Quet toan backend tim chuoi da dich bi nhiem mau "noi chuoi nguon" (artifact).

Cach phat hien: gia tri chuoi chua mau `"<newline><space>"` - day la do phan thang cua
chuoi noi ham (implicit concatenation) bi ghi de bang mot chuoi duy nhat, nen
khoi qua bao boc nam trong gia tri.

    python tools/i18n_messages_scan.py [duong_dan...]
"""
from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / ".msg-work"
ART = re.compile(r'"\s*\r?\n\s*"')

paths = [Path(a) for a in sys.argv[1:]] or [ROOT / "backend"]
files: list[Path] = []
for p in paths:
    files.extend(sorted(p.rglob("*.py")) if p.is_dir() else [p])

rows = []
for f in files:
    if ".venv" in f.parts or "node_modules" in f.parts:
        continue
    try:
        tree = ast.parse(f.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        rows.append({"file": str(f), "line": 0, "error": f"parse: {exc}"})
        continue
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and ART.search(node.value):
            rows.append({
                "file": f.relative_to(ROOT).as_posix(),
                "line": node.lineno,
                "end_line": node.end_lineno,
                "chars": len(node.value),
                "samples": ART.findall(node.value)[:3],
                "preview": node.value[:180].replace("\n", "\\n"),
            })

WORK.mkdir(exist_ok=True)
(WORK / "artifacts.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
print(f"artifact_strings={len(rows)} files={len({r['file'] for r in rows})}")
for r in rows[:40]:
    print(f"{r['file']}:{r.get('line')} L{r.get('end_line')} chars={r.get('chars')} :: {r['preview'][:120]}")
