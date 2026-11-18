"""Khởi tạo (hoặc xác nhận) replica set rs0 một node cho MongoDB cục bộ.

    python tools/rs_init.py [--port 27017]

Thoát: 0 = PRIMARY sẵn sàng ghi, 2 = lỗi khác, 3 = không kết nối được.
"""

from __future__ import annotations

import argparse
import sys
import time

from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, OperationFailure


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=27017)
    args = parser.parse_args()

    client = MongoClient(f"mongodb://127.0.0.1:{args.port}/?directConnection=true",
                         serverSelectionTimeoutMS=8000)
    admin = client["admin"]
    try:
        admin.command("hello")
    except ConnectionFailure as exc:
        print("khong ket noi duoc MongoDB:", exc)
        return 3

    try:
        admin.command("replSetGetStatus")
        print("rs0 da duoc khoi tu truoc do")
    except OperationFailure as exc:
        if exc.code not in (73, 94):  # NotYetInitialized / NoConfigReceived
            print("loi replSetGetStatus bat ngo:", exc)
            return 2
        print("dang khoi tao rs0 ...")
        admin.command("replSetInitiate", {"_id": "rs0", "members": [{"_id": 0, "host": f"127.0.0.1:{args.port}"}]})

    for _ in range(60):
        try:
            status = admin.command("replSetGetStatus")
        except OperationFailure:
            time.sleep(1)
            continue
        if status.get("myState") == 1 or any(m.get("stateStr") == "PRIMARY" for m in status.get("members", [])):
            print("rs0 PRIMARY san sang ghi")
            client.close()
            return 0
        time.sleep(1)

    print("het tro cho PRIMARY (trạng thai hiện tại:", status.get("myState") if status else None, ")", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
