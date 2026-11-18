"""Sua thu cong cac doan f-string noi chen keo (implicit concatenation) ma
tools/i18n_errors.py khong the thay an toan bang offset.

Thay the chuoi THUONG (literal replace, khong regex), moi cap (file, old, new)
phai tim thay it nhat mot lan; khong tim thay = bao loi de khong im lang sot lai.

    python tools/fix_concat_fragments.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

EDITS = [
    (
        "backend/services/novel/character_faction_binding_service.py",
        '"角色—势力绑定端点不存在于当前小说: "',
        '"Điểm cuối liên kết nhân vật—thế lực không tồn tại trong tiểu thuyết hiện tại: "',
    ),
    (
        "backend/services/novel/character_faction_binding_service.py",
        '"角色—势力绑定端点当前不可用: "',
        '"Điểm cuối liên kết nhân vật—thế lực hiện không khả dụng: "',
    ),
    (
        "backend/services/novel/character_faction_binding_service.py",
        '"主归属目标端点当前不可用: "',
        '"Điểm cuối quy thuộc chính hiện không khả dụng: "',
    ),
    (
        "backend/services/novel/character_faction_binding_service.py",
        '"被替换主归属版本集合冲突："',
        '"Tập phiên bản quy thuộc chính bị thay thế xung đột: "',
    ),
    (
        "backend/services/novel/character_faction_binding_service.py",
        "' 不在回收站\"",
        "' không nằm trong thùng rác\"",
    ),
    (
        "backend/services/novel/faction_service.py",
        '"本批不建立直接关系的势力数量与请求不一致: 期望 "',
        '"Số thế lực không tạo quan hệ trực tiếp trong lô này lệch với yêu cầu: kỳ vọng "',
    ),
    (
        "backend/services/novel/faction_service.py",
        '"排序请求必须覆盖当前全部活动核心势力：expected="',
        '"Yêu cầu sắp xếp phải bao phủ toàn bộ thế lực lõi đang hoạt động: expected="',
    ),
    (
        "backend/services/task_flows/provider_references.py",
        '"请先在这些方案中解除引用后再删除"',
        '"Hãy bỏ tham chiếu trong các phương án đó trước khi xóa"',
    ),
    (
        "backend/services/task_flows/provider_references.py",
        '" 仍被任务方案「"',
        '" vẫn bị phương án luồng «"',
    ),
    (
        "backend/services/task_flows/provider_references.py",
        '"」"',
        '"»"',
    ),
    (
        "backend/services/task_flows/provider_references.py",
        '"等 "',
        '"cùng "',
    ),
    (
        "backend/services/task_flows/provider_references.py",
        '" 个方案"',
        '" phương án"',
    ),
]


def main() -> int:
    failures = []
    for rel, old, new in EDITS:
        path = ROOT / rel
        text = path.read_text(encoding="utf-8")
        if old not in text:
            failures.append((rel, old))
            continue
        path.write_text(text.replace(old, new), encoding="utf-8")
    print(f"ap dung={len(EDITS) - len(failures)} khong_tim_thay={len(failures)}")
    for rel, old in failures:
        print("   MISSING", rel, old[:70])
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
