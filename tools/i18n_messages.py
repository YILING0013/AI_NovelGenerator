"""Trích xuất / áp dụng bản dịch cho THÔNG ĐIỆP người dùng trong backend (không phải prompt).

    python tools/i18n_messages.py extract      # .msg-work/segments.json
    python tools/i18n_messages.py apply        # nạp .msg-work/translated.json
    python tools/i18n_messages.py check        # còn bao nhiêu chuỗi Hán chưa dịch

Quy tắc:
* Bỏ qua docstring (là tài liệu cho lập trình viên, không hiển thị cho khách).
* Bỏ qua chuỗi là key của dict, tên enum, và chuỗi xuất hiện trong phép so sánh
  (==, !=, in, not in) vì đó là định danh kỹ thuật.
* Chuỗi f-string: chỉ dịch các phần literal, biểu thức trong {} giữ nguyên.
"""

from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / ".msg-work"
CJK = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")

FILES = [
    "backend/migrations/task_flows.py",
    "backend/migrations/__init__.py",
    "backend/api/error_protocol.py",
    "backend/runtime.py",
    "backend/app.py",
    "backend/services/task_flows/registry.py",
    "backend/services/task_flows/store.py",
    "backend/db/mongo.py",
    "backend/config/config.py",
    "backend/api/default_routers/config_router.py",
    "backend/api/default_routers/runtime_router.py",
    "backend/api/default_routers/export_router.py",
    "backend/api/default_routers/upload_router.py",
    # lop 1b: mo ta truong (description=/examples=) ngoai backend/llm/schemas
    "backend/llm/models.py",
    "backend/llm/config.py",
    "backend/llm/generation_options.py",
    "backend/services/llm/provider_test_service.py",
    "backend/services/task_flows/agent_contract.py",
    "backend/services/task_flows/agent.py",
    "backend/services/novel/chapter_check_contract.py",
    "backend/services/assistant/contracts.py",
    "backend/services/assistant/models.py",
    "backend/services/llm/candidate_contract.py",
    "backend/services/novel/chapter_record_contract.py",
    "backend/services/novel/foreshadowing_contract.py",
    "backend/ops/book_archive.py",
]


def byte_line_starts(raw: bytes):
    starts = [0]
    pos = 0
    while True:
        idx = raw.find(b"\n", pos)
        if idx == -1:
            break
        pos = idx + 1
        starts.append(pos)
    return starts


def protected_ids(tree: ast.Module):
    """id() của các node chuỗi không được dịch: docstring, key dict, operand so sánh,
    tham số của re.* (regex la dinh danh ky thuat, khong phai van ban hien thi)."""
    skip = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", [])
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                if isinstance(body[0].value.value, str):
                    skip.add(id(body[0].value))
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare):
            for side in [node.left, *node.comparators]:
                if isinstance(side, ast.Constant) and isinstance(side.value, str):
                    skip.add(id(side))
        if isinstance(node, ast.Dict):
            for key in node.keys:
                if isinstance(key, ast.Constant) and isinstance(key.value, str):
                    skip.add(id(key))
        if isinstance(node, ast.Call):
            func = node.func
            name = getattr(func, "attr", "") or getattr(func, "id", "")
            holder = getattr(func, "value", None)
            module = getattr(holder, "id", "") if isinstance(holder, ast.Name) else ""
            if name in {"compile", "search", "match", "fullmatch", "sub", "subn", "findall", "split", "finditer"} and module in {"re", ""}:
                for arg in [*node.args, *(kw.value for kw in node.keywords)]:
                    for sub in ast.walk(arg):
                        if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                            skip.add(id(sub))
    return skip


def collect():
    segments = []
    seen = set()
    for rel in FILES:
        path = ROOT / rel
        if not path.exists():
            continue
        raw = path.read_bytes()
        text = raw.decode("utf-8")
        tree = ast.parse(text)
        starts = byte_line_starts(raw)
        skip = protected_ids(tree)

        for node in ast.walk(tree):
            if isinstance(node, ast.JoinedStr):
                for part in node.values:
                    if isinstance(part, ast.Constant) and isinstance(part.value, str) and CJK.search(part.value):
                        seg = _seg(rel, raw, starts, part, skip, fstring=True)
                        if seg and seg["id"] not in seen:
                            seen.add(seg["id"])
                            segments.append(seg)
            elif isinstance(node, ast.Constant) and isinstance(node.value, str) and CJK.search(node.value):
                seg = _seg(rel, raw, starts, node, skip, fstring=False)
                if seg and seg["id"] not in seen:
                    seen.add(seg["id"])
                    segments.append(seg)
    return segments


def _seg(rel, raw, starts, node, skip, *, fstring):
    if id(node) in skip:
        return None
    start = starts[node.lineno - 1] + node.col_offset
    end = starts[node.end_lineno - 1] + node.end_col_offset
    if fstring:
        # phan literal ben trong f-string: span khong chua bao boc
        source = node.value
    else:
        # chong chuoi thuong: gia tri da duoc Python giai ma (khong dau nhay)
        source = node.value
    if not CJK.search(source):
        return None
    return {
        "id": f"{rel}:{node.lineno}:{node.col_offset}",
        "file": rel,
        "start": start,
        "end": end,
        "source": source,
        "fstring": fstring,
        "lines": source.count("\n"),
    }


def _clean_target(text: str, *, fstring: bool) -> str:
    """Loai bao dau nhay bi dai them khi ban dich copy theo dinh dang source cu.

    Cac batch cu duoc giao source da include dau nhay va escape, nen model tra ve
    '"..."', '\\"...\\"' hoac '\\\\n'. Chuan hoa ve van ban thôc trươc khi ghi.
    """
    if fstring:
        return text
    value = text
    value = re.sub(r'"(?:\\r\\n|\\n|"\s*\r?\n\s*)"', "\n", value)
    value = re.sub(r'"\s*\r?\n\s*"', "\n", value)
    changed = True
    while changed and len(value) >= 2:
        changed = False
        if value[0] == '"' and value[-1] == '"':
            value = value[1:-1].replace('\\"', '"')
            changed = True
        elif value.startswith('\\"') and value.endswith('\\"'):
            value = value[2:-2].replace('\\"', '"')
            changed = True
    value = value.replace('\\"', '"')
    # `\n` trong ban dich la newline thuc (json.dumps se escape lai khi ghi file)
    return value.replace("\\\\n", "\n").replace("\\n", "\n").replace("\\t", "\t")


def extract():
    WORK.mkdir(exist_ok=True)
    segments = collect()
    payload = [{"id": s["id"], "file": s["file"], "source": s["source"]} for s in segments]
    (WORK / "segments.json").write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"segments={len(segments)} chars={sum(len(s['source']) for s in segments)}")
    for s in payload[:80]:
        print(f"  {s['id']}\n    {s['source'][:150]}")


def apply():
    # 1) ghep moi nguon dich da co (id -> target)
    table = []
    for f in sorted(WORK.glob("translated*.json")):
        table.extend(json.loads(f.read_text(encoding="utf-8")))
    by_id = {item["id"]: item["target"] for item in table}

    # 2) khi vi tri chuoi doi sau lan ghi truoc, id moi khua khop ban dich;
    #    dung bang nguyen van source -> target de bao dam khong sot lai chu Han.
    by_source = {}
    for name in ("segments.json", "segments_pending.json"):
        path = WORK / name
        if not path.exists():
            continue
        for item in json.loads(path.read_text(encoding="utf-8")):
            target = by_id.get(item["id"])
            if target is not None:
                by_source.setdefault(item["source"], target)
    for f in sorted(WORK.glob("batch*.json")):
        for item in json.loads(f.read_text(encoding="utf-8")):
            target = by_id.get(item["id"])
            if target is not None:
                by_source.setdefault(item["source"], target)

    def lookup(seg):
        if seg["id"] in by_id:
            return by_id[seg["id"]]
        return by_source.get(seg["source"])

    segments = collect()
    per_file: dict[str, list] = {}
    for s in segments:
        if lookup(s) is None:
            continue
        target = _clean_target(by_id[s["id"]], fstring=s["fstring"])
        if s["fstring"]:
            # phan ben trong f-string: span khong chua bao boc, viet thong thuong
            # va nhan doi dau {} de khong bi hieu la bieu thuc.
            if '"' in s["source"] or "'" in s["source"] or "\\" in target:
                continue  # khong an toan de thay, giu nguyen
            body = target.replace("{", "{{").replace("}", "}}")
            literal = body.encode("utf-8")
        else:
            literal = json.dumps(target, ensure_ascii=False).encode("utf-8")
        per_file.setdefault(s["file"], []).append((s["start"], s["end"], literal))
    missing = [s["id"] for s in segments if s["id"] not in by_id]
    for rel, edits in per_file.items():
        raw = (ROOT / rel).read_bytes()
        for start, end, literal in sorted(edits, key=lambda e: -e[0]):
            raw = raw[:start] + literal + raw[end:]
        (ROOT / rel).write_bytes(raw)
    print(f"files={len(per_file)} edits={sum(len(v) for v in per_file.values())} missing={len(missing)}")
    for m in missing[:15]:
        print("  chưa dịch:", m)


def check():
    segments = collect()
    print(f"segments_con_CJK={len(segments)} chars={sum(len(s['source']) for s in segments)}")
    for s in segments[:30]:
        print(f"  {s['id']}: {s['source'][:120]}")


def pending():
    """Ghi .msg-work/segments_pending.json: những chuỗi chưa có bản dich."""
    done = set()
    tr = WORK / "translated.json"
    if tr.exists():
        done = {x["id"] for x in json.loads(tr.read_text(encoding="utf-8"))}
    segs = [s for s in collect() if s["id"] not in done]
    payload = [{"id": s["id"], "file": s["file"], "fstring": s["fstring"], "source": s["source"]} for s in segs]
    (WORK / "segments_pending.json").write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"pending={len(payload)} chars={sum(len(p['source']) for p in payload)}")
    for p in payload:
        print(f"  {p['id']}\n    {p['source'][:160]}")


FW_PUNCT = {
    "：": ": ",
    "；": "; ",
    "，": ", ",
    "、": ", ",
    "。": ".",
    "！": "!",
    "？": "?",
    "（": " (",
    "）": ") ",
    "「": '"',
    "」": '"',
    "『": '"',
    "』": '"',
    "，": ", ",
}


def normalize_punct():
    """Doi dau cau Trung Hoa sang dau cau thuong trong chuoi DA dich (khong con chu Han)."""
    files = {}
    for rel in FILES:
        path = ROOT / rel
        if not path.exists():
            continue
        raw = path.read_bytes()
        text = raw.decode("utf-8")
        tree = ast.parse(text)
        starts = byte_line_starts(raw)
        edits = []
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
                continue
            if CJK.search(node.value):
                continue
            if not any(ch in node.value for ch in FW_PUNCT):
                continue
            new_value = node.value
            for src_ch, dst in FW_PUNCT.items():
                new_value = new_value.replace(src_ch, dst)
            start = starts[node.lineno - 1] + node.col_offset
            end = starts[node.end_lineno - 1] + node.end_col_offset
            edits.append((start, end, json.dumps(new_value, ensure_ascii=False).encode("utf-8")))
        if edits:
            for start, end, literal in sorted(edits, key=lambda e: -e[0]):
                raw = raw[:start] + literal + raw[end:]
            path.write_bytes(raw)
            files[rel] = len(edits)
    print("chuoi da chuan hoa dau cau:", files)


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass
    cmd = sys.argv[1] if len(sys.argv) > 1 else "check"
    {"extract": extract, "apply": apply, "check": check, "pending": pending, "normalize": normalize_punct}[cmd]()
