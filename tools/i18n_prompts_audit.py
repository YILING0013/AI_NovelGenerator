"""Sau khi apply: doi chieu file dang chay voi ban goc trong git.

    python tools/i18n_prompts_audit.py            # audit toan bo file da doi
    python tools/i18n_prompts_audit.py --limit 40 # in them chi tiet loi

Kiem tra:
  1. JSON/Python parse duoc.
  2. Tap placeholder {var} / {{var}} khong doi so voi ban goc (truong hop md).
  3. Khong con ky tu Han (bao cao soi bo, co the con voi logo/duong dan).
  4. Voi JSON: so luong key va ten key cap 1 cua moi object khong doi (chot chan cap nhat cau truc).
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CJK = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
PH = re.compile(r"\{[A-Za-z_][A-Za-z0-9_]{0,40}\}")


def git_show(path: str) -> str:
    return subprocess.run(["git", "show", f"HEAD:{path}"], capture_output=True, cwd=ROOT).stdout.decode("utf-8")


def changed_files() -> list[str]:
    out = subprocess.run(["git", "diff", "--name-only", "HEAD"], capture_output=True, cwd=ROOT).stdout.decode("utf-8")
    return [line.strip() for line in out.splitlines() if line.strip()]


def key_shape(node, depth=0, trail=""):
    """Tap duong dan key den do sau 4 de phat hien mat key."""
    keys = set()
    if isinstance(node, dict):
        for k, v in node.items():
            keys.add(trail + k)
            if depth < 4:
                keys |= key_shape(v, depth + 1, trail + k + ".")
    elif isinstance(node, list):
        for item in node[:60]:
            if depth < 4:
                keys |= key_shape(item, depth + 1, trail)
    return keys


# name/label/title la khoa tra cuu i18n cua frontend nen GIU NGUYEN tieng Trung.
PROTECTED_LEAF_KEYS = {"id", "task", "type", "label", "name", "node_id", "ref", "key",
                       "prompt_ref", "provider", "model", "format_version", "revision",
                       "edge_id", "title"}


def cjk_in_translatable(node, path=""):
    """Dem ky tu Han trong gia tri o key KHONG duoc bao ve."""
    total = 0
    if isinstance(node, dict):
        for k, v in node.items():
            if isinstance(v, str):
                if k not in PROTECTED_LEAF_KEYS:
                    total += len(CJK.findall(v))
            else:
                total += cjk_in_translatable(v, f"{path}.{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            if isinstance(v, str):
                total += len(CJK.findall(v))
            else:
                total += cjk_in_translatable(v, f"{path}[{i}]")
    return total


def main() -> int:
    limit = 40
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])
    problems = []
    files = changed_files()
    for rel in files:
        p = ROOT / rel
        if not p.exists():
            problems.append(f"{rel}: file bi mat")
            continue
        text = p.read_text(encoding="utf-8")
        try:
            base = git_show(rel)
        except Exception as exc:  # noqa: BLE001
            problems.append(f"{rel}: khong doc duoc git HEAD {exc}")
            continue
        if rel.endswith(".json"):
            try:
                new_data = json.loads(text)
                old_data = json.loads(base)
            except Exception as exc:  # noqa: BLE001
                problems.append(f"{rel}: JSON loi {exc}")
                continue
            lost = key_shape(old_data) - key_shape(new_data)
            gained = key_shape(new_data) - key_shape(old_data)
            if lost:
                problems.append(f"{rel}: mat {len(lost)} key: {sorted(lost)[:5]}")
            if gained:
                problems.append(f"{rel}: thu them {len(gained)} key: {sorted(gained)[:5]}")
            if cjk_in_translatable(new_data):
                problems.append(f"{rel}: con {cjk_in_translatable(new_data)} ky tu Han o key khong duoc bao ve")
        elif rel.endswith(".py"):
            import ast

            try:
                ast.parse(text)
            except Exception as exc:  # noqa: BLE001
                problems.append(f"{rel}: Python loi {exc}")
                continue
        elif rel.endswith(".md"):
            old_ph = sorted(set(PH.findall(base)))
            new_ph = sorted(set(PH.findall(text)))
            if old_ph != new_ph:
                problems.append(f"{rel}: placeholder doi: mat {set(old_ph) - set(new_ph)}, them {set(new_ph) - set(old_ph)}")
            if text.count("\n") != base.count("\n"):
                problems.append(f"{rel}: so dong doi {base.count(chr(10))} -> {text.count(chr(10))}")
            if CJK.search(text):
                problems.append(f"{rel}: con {len(CJK.findall(text))} ky tu Han")
    print(f"files_changed={len(files)} problems={len(problems)}")
    for p in problems[:limit]:
        print("  ", p)
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
