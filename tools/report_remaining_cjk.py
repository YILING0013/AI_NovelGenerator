"""Phân loại các chuỗi còn tiếng Trung theo bối cảnh và thư mục (báo cáo cho khách)."""

from __future__ import annotations

import json
import pathlib
import re
import sys
from collections import Counter

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from i18n_errors import all_segments, coupled_texts  # noqa: E402

# noqa: E402

CJK = re.compile(r"[\u3400-\u9fff]")


def main() -> int:
    rows = all_segments()
    kinds: Counter = Counter()
    dirs: Counter = Counter()
    for r in rows:
        kinds[r["kind"]] += len(r["source"])
        dirs[str(pathlib.Path(r["file"]).parts[1] if len(pathlib.Path(r["file"]).parts) > 2 else r["file"])] += len(
            r["source"]
        )
    print("== CHUOI TINH (literal trong ma) ==")
    print(" ky tu theo kind:", dict(kinds))
    print(" ky tu theo thu muc:", dict(dirs.most_common(8)))
    # Đếm comment/docstring thường (không phải khách hàng thấy)
    comment_chars = 0
    for p in pathlib.Path("backend").rglob("*.py"):
        try:
            text = p.read_text(encoding="utf-8")
        except Exception:  # noqa: BLE001
            continue
        for m in re.finditer(r"^\s*#.*$", text, re.M):
            comment_chars += len(CJK.findall(m.group()))
    print(" ky tu Han trong comment Python:", comment_chars)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
