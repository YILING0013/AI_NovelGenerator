"""Kiem tra nhanh: MongoDB ghi doc duoc, backend/API phan hoi tieng Viet.

    python tools/smoke_app.py            # dung cong mac dinh 27017/8200/3300
    python tools/smoke_app.py --mongo-port 27020

 thoat 0 neu tat ca buoc dat.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request

from pymongo import MongoClient

CJK = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")


def http_json(url: str, timeout: float = 25.0):
    with urllib.request.urlopen(url, timeout=timeout) as response:  # noqa: S310
        return response.status, json.loads(response.read().decode("utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mongo-port", type=int, default=27017)
    parser.add_argument("--backend-port", type=int, default=8200)
    parser.add_argument("--frontend-port", type=int, default=3300)
    args = parser.parse_args()

    failures = []

    # 1. MongoDB: replica set + ghi doc
    try:
        client = MongoClient(f"mongodb://127.0.0.1:{args.mongo_port}/?replicaSet=rs0&directConnection=true",
                             serverSelectionTimeoutMS=15000)
        state = client.admin.command("replSetGetStatus").get("myState")
        print(f"[1/4] MongoDB rs0 myState={state} (1 = PRIMARY)")
        if state != 1:
            failures.append("MongoDB khong phai PRIMARY")
        probe = client["smoke_test"]["probe"]
        marker = "smoke-ok"
        probe.delete_many({})
        probe.insert_one({"marker": marker})
        got = probe.find_one({"marker": marker})
        print("[2/4] Ghi/doc thu nghiem:", "OK" if got else "FAIL")
        if not got:
            failures.append("khong doc duoc sau khi ghi")
        probe.delete_many({})
        client.close()
    except Exception as exc:  # noqa: BLE001
        print(f"[1/4] MongoDB LOI: {exc}")
        failures.append("MongoDB khong khot")

    # 2. Backend: startup + task list
    base = f"http://127.0.0.1:{args.backend_port}"
    try:
        status, body = http_json(f"{base}/api/task-flows/tasks")
        tasks = body.get("tasks", []) if isinstance(body, dict) else body
        label = tasks[0]["label"] if tasks else ""
        cjk = len(CJK.findall(json.dumps(tasks, ensure_ascii=False)))
        print(f"[3/4] Backend /api/task-flows/tasks status={status} tasks={len(tasks)} chu_Han_trong_response={cjk}")
        print(f"       vi du label: {label}")
        if status != 200 or not tasks:
            failures.append("backend tasks API loi")
    except Exception as exc:  # noqa: BLE001
        print(f"[3/4] Backend LOI: {exc}")
        failures.append("backend khong phan hoi")

    # 3. Frontend: trang tieng Viet
    try:
        url = f"http://127.0.0.1:{args.frontend_port}/vi"
        with urllib.request.urlopen(url, timeout=60) as response:  # noqa: S310
            html = response.read().decode("utf-8", "replace")
            lang = re.search(r'<html lang="([a-z-]+)"', html)
            has_vi = "Ti\u1ebfng Vi\u1ec7t" in html or "Cài đặt" in html or "Giá sách" in html
            print(f"[4/4] Frontend {url} status={response.status} lang={lang.group(1) if lang else '?'} tieng_viet={has_vi}")
            if response.status != 200 or not has_vi:
                failures.append("frontend khong tra giao dien tieng Viet")
    except Exception as exc:  # noqa: BLE001
        print(f"[4/4] Frontend LOI: {exc}")
        failures.append("frontend khong phan hoi")

    print("\nKET QUA:", "PASS" if not failures else "FAIL -> " + "; ".join(failures))
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
