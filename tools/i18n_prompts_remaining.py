"""In danh sach file unit CHUA co ban dich, co the chia thanh N phong.

    python tools/i18n_prompts_batches.py remaining [N]
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UNITS = ROOT / ".promo-work" / "units"
TRANS = ROOT / ".promo-work" / "translated"

done = set()
if TRANS.exists():
    for f in TRANS.glob("*.json"):
        done.add(f.name)

remaining = sorted(f.name for f in UNITS.glob("*.json") if f.name not in done)
if not remaining:
    print("ALL DONE")
    raise SystemExit(0)

n = int(sys.argv[2]) if len(sys.argv) > 2 else 1
size = sum(1 for _ in remaining)
print(f"remaining_units={size}")
# ưu tiên unit lớn trước
def chars(name):
    data = json.loads((UNITS / name).read_text(encoding="utf-8"))
    return sum(len(s["source"]) for s in data["segments"])

remaining.sort(key=chars, reverse=True)
buckets = [[] for _ in range(n)]
load = [0] * n
for name in remaining:
    i = load.index(min(load))
    buckets[i].append(name)
    load[i] += chars(name)
for i, b in enumerate(buckets):
    print(f"\n### SLOT {i} (chars~{load[i]})")
    for name in b:
        print(name)
