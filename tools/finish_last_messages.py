"""Dịch nốt các chuỗi xung đột phiên bản / luồng ngắt sớm còn sót (theo DÒNG cụ thể).

Thay thế chuỗi tuyệt đối (literal) và kiểm tra đúng dòng để không đụng docstring kỹ thuật.
"""

from __future__ import annotations

import pathlib
import sys

# (file, dong, chuoi cu, chuoi moi)
EDITS: list[tuple[str, int, str, str]] = [
    # Khoa phat hien: chap nhan ca cau tieng Viet.
    ("backend/api/default_routers/faction_router.py", 426,
     'if "版本冲突" in message else "FACTION_CONFLICT"',
     'if ("版本冲突" in message or "xung đột phiên bản" in message) else "FACTION_CONFLICT"'),
    ("backend/api/default_routers/character_faction_binding_router.py", 286,
     'if "版本冲突" in message else "BINDING_CONFLICT"',
     'if ("版本冲突" in message or "xung đột phiên bản" in message) else "BINDING_CONFLICT"'),
    # Manh f-string trong thong bao loi.
    ("backend/db/repositories/character_faction_binding_repository.py", 494, "版本冲突：", "xung đột phiên bản: "),
    ("backend/db/repositories/character_relation_repository.py", 362, "版本冲突：", "xung đột phiên bản: "),
    ("backend/db/repositories/faction_relation_repository.py", 393, "版本冲突：", "xung đột phiên bản: "),
    ("backend/db/repositories/faction_repository.py", 430, "版本冲突：", "xung đột phiên bản: "),
    ("backend/db/repositories/faction_repository.py", 581, "版本冲突：", "xung đột phiên bản: "),
    ("backend/services/novel/character_faction_binding_service.py", 740, "版本冲突：", "xung đột phiên bản: "),
    ("backend/services/novel/character_relation_service.py", 253, "版本冲突：", "xung đột phiên bản: "),
    ("backend/services/novel/faction_relation_service.py", 227, "版本冲突：", "xung đột phiên bản: "),
    ("backend/services/novel/faction_relation_service.py", 600, "AI 阵营关系候选依据版本冲突: ",
     "Xung đột phiên bản căn cứ của ứng viên quan hệ thế lực do AI tạo: "),
    ("backend/services/novel/faction_service.py", 273, "势力版本冲突：", "Xung đột phiên bản thế lực: "),
    ("backend/services/novel/faction_service.py", 274, "当前版本为", "phiên bản hiện tại là"),
    ("backend/services/novel/faction_service.py", 1573, "版本冲突：", "xung đột phiên bản: "),
    ("backend/services/novel/item_service.py", 544, "版本冲突", "xung đột phiên bản"),
    ("backend/services/novel/item_service.py", 1151, "版本冲突", "xung đột phiên bản"),
    ("backend/services/novel/location_service.py", 897, "版本冲突", "xung đột phiên bản"),
    ("backend/services/novel/location_service.py", 2055, "版本冲突", "xung đột phiên bản"),
    ("backend/services/novel/world_rule_service.py", 594, "版本冲突", "xung đột phiên bản"),
    ("backend/services/novel/volume_service.py", 550, "卷版本冲突：当前版本为",
     "xung đột phiên bản tập: phiên bản hiện tại là"),
    # LLM kết nối bị ngắt sớm (provider_test_service chấp nhận cả tiếng Việt).
    ("backend/llm/claude_client.py", 223, "Claude 响应流提前断开，请重试", "Luồng phản hồi Claude bị ngắt sớm, vui lòng thử lại"),
    ("backend/llm/claude_client.py", 422, "Claude 响应流提前断开，请重试", "Luồng phản hồi Claude bị ngắt sớm, vui lòng thử lại"),
    ("backend/llm/responses_client.py", 72, "Responses 响应流提前断开，请重试", "Luồng phản hồi Responses bị ngắt sớm, vui lòng thử lại"),
    ("backend/llm/responses_client.py", 159, "响应流提前断开，请重试", "Luồng phản hồi bị ngắt sớm, vui lòng thử lại"),
]


def main() -> int:
    problems: list[str] = []
    lines_by_file: dict[str, list[str]] = {}
    for rel, lineno, old, new in EDITS:
        if rel not in lines_by_file:
            lines_by_file[rel] = pathlib.Path(rel).read_text(encoding="utf-8").splitlines(keepends=True)
        buf = lines_by_file[rel]
        idx = lineno - 1
        if idx >= len(buf) or old not in buf[idx]:
            problems.append(f"{rel}:{lineno} khong chua {old!r}")
            continue
        buf[idx] = buf[idx].replace(old, new, 1)
    for msg in problems:
        print("LOI", msg)
    if problems:
        return 1
    for rel, buf in lines_by_file.items():
        pathlib.Path(rel).write_text("".join(buf), encoding="utf-8")
        print("OK ", rel)
    print(f"edits={len(EDITS)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
