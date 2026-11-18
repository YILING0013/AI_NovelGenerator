"""Xem task flow trong MongoDB có snapshot schema tiếng Trung (cũ) hay không.

Backend có thể trả schema đã lưu sẵn lúc seed, không đọc lại mã nguồn -> cần làm mới DB.
"""

from __future__ import annotations

import json
import re

from pymongo import MongoClient

CJK = re.compile(r"[\u3400-\u9fff]")

client = MongoClient("mongodb://127.0.0.1:27017/?replicaSet=rs0&directConnection=true")
db = client["novel_generator"]
print("database:", db.name, "| collections:", db.list_collection_names())
for name in db.list_collection_names():
    coll = db[name]
    total = coll.count_documents({})
    with_cjk = 0
    sample = None
    for doc in coll.find({}, {"_id": 1}).limit(400):
        full = coll.find_one({"_id": doc["_id"]})
        text = json.dumps(full, ensure_ascii=False)
        if CJK.search(text):
            with_cjk += 1
            if sample is None:
                m = CJK.search(text)
                sample = text[max(0, m.start() - 60) : m.start() + 60]
    print(f"  {name:28s} docs={total:5d} con_Han={with_cjk}")
    if sample:
        print("      vi du:", sample.replace("\n", " ")[:150])
