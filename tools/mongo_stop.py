"""Tat MongoDB mot cach thuong (tranh shut down cuong bang).

Dung:
    python tools/mongo_stop.py [--port 27017]

Shutdown lam dat file log cua chinh mongod (ket noi bi dong), do do loi duoc in ra
dinh kem ma thoat: 0 = da dung, 2 = that bai, 3 = khong co server nao o cong nay.
"""

from __future__ import annotations

import argparse
import socket
import sys

from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=27017)
    args = parser.parse_args()

    probe = socket.socket()
    probe.settimeout(1.5)
    try:
        probe.connect(("127.0.0.1", args.port))
    except OSError:
        print(f"khong co MongoDB nao nghe o cong {args.port}")
        return 3
    finally:
        probe.close()

    client = MongoClient(f"mongodb://127.0.0.1:{args.port}/?directConnection=true",
                         serverSelectionTimeoutMS=8000, connectTimeoutMS=5000)
    try:
        client["admin"].command({"shutdown": 1})
    except (ConnectionFailure, ServerSelectionTimeoutError):
        # mongod dong ket noi ngay khi chap nhan lenh shutdown -> xem nhu thanh cong
        pass
    except Exception as exc:  # noqa: BLE001
        print(f"shutdown that bai: {exc}", file=sys.stderr)
        return 2

    for _ in range(40):
        check = socket.socket()
        check.settimeout(1)
        try:
            check.connect(("127.0.0.1", args.port))
            connected = True
        except OSError:
            connected = False
        finally:
            check.close()
        if not connected:
            print(f"MongoDB (cong {args.port}) da dung tuong thanh")
            return 0
    print(f"MongoDB van con nghe o cong {args.port}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
