"""Chia các unit dịch prompt thành từng lô nhỏ (mặc định <= 7000 ký tự nguồn/lô).

Cách dùng:
    python tools/i18n_prompts_batches.py plan [MAX_CHARS]
    python tools/i18n_prompts_batches.py status     # lô nào đã có bản dich
    python tools/i18n_prompts_batches.py todo       # in danh sach file cua cac lô chua xong
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UNITS = ROOT / ".promo-work" / "units"
TRANS = ROOT / ".promo-work" / "translated"
BATCHES = ROOT / ".promo-work" / "batches.json"


def plan(max_chars=7000):
    manifests = []
    for f in sorted(UNITS.glob("*.json")):
        data = json.loads(f.read_text(encoding="utf-8"))
        size = sum(len(s["source"]) for s in data["segments"])
        manifests.append({"file": f.name, "id": data["id"], "kind": data["kind"], "chars": size,
                          "segments": len(data["segments"])})
    manifests.sort(key=lambda m: -m["chars"])
    batches, current, cur_chars = [], [], 0
    for m in manifests:
        if current and cur_chars + m["chars"] > max_chars:
            batches.append(current)
            current, cur_chars = [], 0
        current.append(m)
        cur_chars += m["chars"]
    if current:
        batches.append(current)
    payload = [{"index": i, "max_chars": sum(m["chars"] for m in b), "files": [m["file"] for m in b]}
               for i, b in enumerate(batches)]
    BATCHES.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"batches={len(payload)} max={max_chars}")
    for b in payload:
        print(f"batch {b['index']:>2}  chars={b['max_chars']:>6}  files={len(b['files'])}")
    return payload


def done_ids():
    return {json.loads(f.read_text(encoding="utf-8"))["id"] for f in TRANS.glob("*.json")} if TRANS.exists() else set()


def status():
    batches = json.loads(BATCHES.read_text(encoding="utf-8"))
    done = done_ids()
    for b in batches:
        files = [json.loads((UNITS / f).read_text(encoding="utf-8"))["id"] for f in b["files"]]
        rest = [f for f in files if f not in done]
        print(f"batch {b['index']:>2}: {len(files) - len(rest)}/{len(files)} done" + (f" | con: {', '.join(rest)}" if rest else ""))


def todo():
    batches = json.loads(BATCHES.read_text(encoding="utf-8"))
    done = done_ids()
    for b in batches:
        rest = [f for f in b["files"] if json.loads((UNITS / f).read_text(encoding="utf-8"))["id"] not in done]
        if rest:
            print(f"batch {b['index']}:")
            for f in rest:
                print("   .promo-work/units/" + f)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "plan"
    if cmd == "plan":
        plan(int(sys.argv[2]) if len(sys.argv) > 2 else 7000)
    elif cmd == "status":
        status()
    elif cmd == "todo":
        todo()
