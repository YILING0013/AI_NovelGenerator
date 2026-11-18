"""Kiem tra nhanh bang quy doi thong diep dinh dang cua pydantic sang tieng Viet.

    python tools/test_validation_messages.py

thoat 0 neu toi thieu cac cau lenh dau vao thuong gap deu ra tieng Viet.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.api.error_protocol import translate_validation_message  # noqa: E402

CASES = [
    ("Field required", "Trường này là bắt buộc"),
    ("Extra inputs are not permitted", None),
    ("String should have at least 1 characters", "Chuỗi phải có ít nhất 1 ký tự"),
    ("String should have at most 20000 characters", "Chuỗi phải có nhiều nhất 20000 ký tự"),
    ("Input should be a valid integer", "Đầu vào phải là số nguyên hợp lệ"),
    ("Input should be a valid integer, got not_a_number", "Đầu vào phải là số nguyên hợp lệ, nhưng nhận được not_a_number"),
    ("Input should be a valid string", "Đầu vào phải là chuỗi hợp lệ"),
    ("Input should be 'novel' or 'volume'", None),
    ("Value error, custom text", "Giá trị không hợp lệ: custom text"),
    ("JSON input should be string, bytes or bytearray", None),
    ("List should have at most 5 items", "Danh sách phải có nhiều nhất 5 phần tử"),
]


def main() -> int:
    failures = []
    for source, expected in CASES:
        got = translate_validation_message(source)
        cjk_free = all(ord(ch) < 0x3400 or ord(ch) > 0x9fff for ch in got)
        ascii_fallback = got == source and source not in {"", " "}
        if not cjk_free:
            failures.append((source, got, "con chu Han"))
        elif expected is not None and got != expected:
            failures.append((source, got, f"kỳ vọng: {expected}"))
        elif ascii_fallback and source[:5] in {"Field", "Input", "Value", "Extra", "Strin", "List", "JSON "}:
            failures.append((source, got, "giu nguyen tieng Anh"))
    for source, got, why in failures:
        print(f"FAIL {source!r} -> {got!r} ({why})")
    print(f"cases={len(CASES)} failures={len(failures)}")
    return 0 if not failures else 1


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass
    sys.exit(main())
