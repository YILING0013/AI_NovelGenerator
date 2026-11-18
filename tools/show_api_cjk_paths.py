"""Liệt kê các giá trị còn Hán tự trong response /api/task-flows/tasks kèm đường dẫn JSON."""

from __future__ import annotations

import json
import re
import sys
import urllib.request

CJK = re.compile(r"[\u3400-\u9fff]")


def walk(node, path: str, out: list[tuple[str, str]]):
    if isinstance(node, dict):
        for k, v in node.items():
            walk(v, f"{path}.{k}", out)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            walk(v, f"{path}[{i}]", out)
    elif isinstance(node, str) and CJK.search(node):
        out.append((path, node[:80]))


with urllib.request.urlopen("http://127.0.0.1:8200/api/task-flows/tasks", timeout=60) as resp:
    payload = json.load(resp)

hits: list[tuple[str, str]] = []
walk(payload, "$", hits)
print("so truong con Han tu:", len(hits))
seen: set[str] = set()
for path, val in hits:
    key = path.split(".")[-1]
    if key in seen:
        continue
    seen.add(key)
    print(f"  khoa `{key}` duong dan {path[:110]} = {val!r}")
