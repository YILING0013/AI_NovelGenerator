"""Tách .msg-work/segments_pending.json thành các lô cho nhiều nhóm dịch song song.

    python tools/i18n_messages_split.py [SO_LO]

Mỗi lô ghi .msg-work/batchNN.json với phần tử {id, file, fstring, source}.
Một file luôn nằm trọn trong một lô để việc kiểm soát dễ hơn.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / ".msg-work"

n = int(sys.argv[1]) if len(sys.argv) > 1 else 3
segs = json.loads((WORK / "segments_pending.json").read_text(encoding="utf-8"))

by_file: dict[str, list] = {}
for s in segs:
    by_file.setdefault(s["file"], []).append(s)
groups = sorted(by_file.values(), key=lambda g: -sum(len(x["source"]) for x in g))

buckets = [[] for _ in range(n)]
load = [0] * n
for g in groups:
    size = sum(len(x["source"]) for x in g)
    i = load.index(min(load))
    buckets[i].extend(g)
    load[i] += size

for i, b in enumerate(buckets):
    (WORK / f"batch{i:02d}.json").write_text(json.dumps(b, ensure_ascii=False, indent=1), encoding="utf-8")
    files = sorted({x["file"] for x in b})
    print(f"batch{i:02d}: items={len(b)} chars={load[i]}")
    for f in files:
        print("      ", f)
