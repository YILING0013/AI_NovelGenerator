"""In ra các dòng còn chứa chữ Hán trong mã Python backend (kèm loại boi cảnh).

    python tools/list_leftover_cjk.py            # chi liet ke chuoi trong boi canh dich duoc
    python tools/list_leftover_cjk.py --all      # ca chu thich/code comment
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from i18n_errors import all_segments, coupled_texts, has_cjk  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--all", action="store_true")
    args = parser.parse_args()

    coupled = coupled_texts()
    rows = []
    for seg in all_segments():
        if any(c in seg["source"] for c in coupled):
            continue
        rows.append(seg)
    print(f"segment_con_chu_Han={len(rows)} ky_tu={sum(len(r['source']) for r in rows)}")
    for r in rows:
        print(f"{r['file']}:{r['line']} [{r['kind']}]\n    {r['source']!r}")
    if args.all:
        cjk = __import__("re").compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")
        count = 0
        for path in sorted((ROOT / "backend").rglob("*.py")):
            for index, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if cjk.search(line):
                    count += 1
        print(f"(thong ke) dong chua chu Han trong backend = {count}")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass
    sys.exit(main())
