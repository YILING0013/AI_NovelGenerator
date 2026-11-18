"""Kiểm chứng bản dịch prompt trong `backend/services/task_flows/defaults/`.

- *.md: so khớp placeholder {x} với bản gốc trong HEAD; phát hiện còn Hán tự.
- *.json: chắc chắn các khoá nghiệp vụ (title/label/name/type/key/options/default) không đổi;
  chỉ từ điển `description` được phép đổi; placeholder trong gia trị đổi phải khớp.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from i18n_prompts import PROTECTED_KEYS, extract_descriptions  # noqa: E402

D = "backend/services/task_flows/defaults"
PLACEHOLDER = re.compile(r"\{([a-zA-Z0-9_\.\[\]]+)\}")
CJK = re.compile(r"[\u3400-\u9fff\uf900-\ufaff]")


def head_text(rel: str) -> str | None:
    r = subprocess.run(
        ["git", "show", f"HEAD:{rel}"], capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    return r.stdout if r.returncode == 0 else None


problems: list[str] = []
md = jsonn = 0
files = subprocess.run(["git", "ls-files", D], capture_output=True, text=True, encoding="utf-8").stdout.split()
for rel in files:
    p = Path(rel)
    cur = p.read_text(encoding="utf-8")
    orig = head_text(rel)
    if orig is None:
        problems.append(f"{rel}: khong tim thay ban HEAD")
        continue
    if p.suffix == ".md":
        md += 1
        a, b = sorted(set(PLACEHOLDER.findall(orig))), sorted(set(PLACEHOLDER.findall(cur)))
        if a != b:
            problems.append(f"{rel}: placeholder {a} -> {b}")
        n = len(CJK.findall(cur))
        if n:
            problems.append(f"{rel}: con {n} ky tu Han")
    elif p.suffix == ".json":
        jsonn += 1
        try:
            po = json.loads(orig)
        except Exception as exc:  # noqa: BLE001
            problems.append(f"{rel}: HEAD khong parse duoc {exc}")
            continue
        pb = json.loads(cur)
        do, dn = extract_descriptions(po), extract_descriptions(pb)
        if {k for k, _ in do} != {k for k, _ in dn}:
            problems.append(f"{rel}: duong dan description khong khop")
        for path in PROTECTED_KEYS:
            a = po[path[:-1].split(".")] if False else None
        for path in PROTECTED_KEYS:
            keys = path.split(".")
            node_o, node_b = po, pb
            ok = True
            for k in keys:
                if isinstance(node_o, dict) and k in node_o:
                    node_o, node_b = node_o[k], node_b.get(k)
                else:
                    ok = False
                    break
            if ok and node_o != node_b:
                problems.append(f"{rel}: khoa bao ve `{path}` bi doi")
        for (path, old), (_, new) in zip(do, dn):
            if old == new:
                continue
            if len(PLACEHOLDER.findall(old)) != len(PLACEHOLDER.findall(new)):
                problems.append(f"{rel}: placeholder lech o {path}")
print(f"md={md} json={jsonn} problems={len(problems)}")
for m in problems[:40]:
    print(" -", m)
