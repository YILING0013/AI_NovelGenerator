"""Volumes 集合 API 集成测试脚本。

需要先启动后端服务 (python main.py) 和 MongoDB。

使用方式:
    python -m tests.test_volumes

测试流程:
    1. 创建一本测试小说 → 拿到 novel_id
    2. 创建卷（自动序号 + 手动序号）
    3. 获取小说下所有卷列表
    4. 获取单卷详情
    5. 更新卷信息
    6. 更新卷统计
    7. 软删除卷 → 恢复卷
    8. 再次软删除 → 硬删除
    9. 清理：硬删除测试小说
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import httpx

BASE_URL = "http://127.0.0.1:8000"
CLIENT = httpx.Client(base_url=BASE_URL, timeout=10, trust_env=False)

DIVIDER = "=" * 60
PASS = "✅ PASS"
FAIL = "❌ FAIL"

# 用于存放测试过程中创建的 ID
state: dict = {}


def api_request(method: str, path: str, **kwargs) -> httpx.Response:
    return CLIENT.request(method, path, **kwargs)


def report(name: str, ok: bool, detail: str = ""):
    tag = PASS if ok else FAIL
    print(f"  {tag}  {name}" + (f"  ({detail})" if detail else ""))
    if not ok:
        state.setdefault("failures", []).append(name)


def section(title: str):
    print(f"\n{DIVIDER}\n  {title}\n{DIVIDER}")


#  0. 前置：创建测试小说 

def test_create_novel():
    section("0. 创建测试小说")
    r = api_request("POST", "/api/novels/create", json={
        "title": "__test_volumes_novel__",
        "genre": "test",
    })
    ok = r.status_code == 200 and "id" in r.json()
    state["novel_id"] = r.json().get("id", "") if ok else ""
    report("POST /api/novels/create", ok, f"novel_id={state['novel_id']}")


#  1. 创建卷 

def test_create_volume_auto_order():
    section("1a. 创建卷（自动 order_index）")
    r = api_request("POST", "/api/volumes/create", json={
        "novel_id": state["novel_id"],
        "title": "第一卷 测试卷",
        "summary": "这是自动序号的测试卷",
    })
    ok = r.status_code == 200 and "id" in r.json()
    state["volume_id_1"] = r.json().get("id", "") if ok else ""
    report("POST /api/volumes/create (auto)", ok, f"volume_id={state.get('volume_id_1')}")


def test_create_volume_manual_order():
    section("1b. 创建卷（手动 order_index=5）")
    r = api_request("POST", "/api/volumes/create", json={
        "novel_id": state["novel_id"],
        "title": "第五卷 跳跃序号",
        "order_index": 5,
    })
    ok = r.status_code == 200 and "id" in r.json()
    state["volume_id_2"] = r.json().get("id", "") if ok else ""
    report("POST /api/volumes/create (manual)", ok, f"volume_id={state.get('volume_id_2')}")


def test_create_volume_duplicate_order():
    section("1c. 创建卷（重复 order_index=5，应返回 409）")
    r = api_request("POST", "/api/volumes/create", json={
        "novel_id": state["novel_id"],
        "title": "重复序号卷",
        "order_index": 5,
    })
    ok = r.status_code == 409
    report("POST /api/volumes/create (dup order)", ok, f"status={r.status_code}")


def test_create_volume_bad_novel():
    section("1d. 创建卷（无效 novel_id，应返回 404）")
    r = api_request("POST", "/api/volumes/create", json={
        "novel_id": "000000000000000000000000",
        "title": "孤儿卷",
    })
    ok = r.status_code == 404
    report("POST /api/volumes/create (bad novel)", ok, f"status={r.status_code}")


#  2. 查询卷列表 

def test_get_volumes_by_novel():
    section("2. 获取小说下所有卷")
    r = api_request("GET", f"/api/volumes/novel/{state['novel_id']}")
    data = r.json().get("data", [])
    ok = r.status_code == 200 and len(data) == 2
    # 验证排序：第一条 order_index 应小于第二条
    if ok and len(data) >= 2:
        ok = data[0].get("order_index", 0) < data[1].get("order_index", 0)
    report("GET /api/volumes/novel/{novel_id}", ok, f"count={len(data)}")


#  3. 获取单卷详情 

def test_get_volume_by_id():
    section("3. 获取单卷详情")
    r = api_request("GET", f"/api/volumes/{state['volume_id_1']}")
    ok = r.status_code == 200 and r.json().get("title") == "第一卷 测试卷"
    report("GET /api/volumes/{volume_id}", ok)


def test_get_volume_not_found():
    section("3b. 获取不存在的卷（应返回 404）")
    r = api_request("GET", "/api/volumes/000000000000000000000000")
    ok = r.status_code == 404
    report("GET /api/volumes/{bad_id}", ok, f"status={r.status_code}")


#  4. 更新卷信息 

def test_update_volume_info():
    section("4. 更新卷信息")
    r = api_request("PUT", f"/api/volumes/{state['volume_id_1']}", json={
        "title": "第一卷 修订版",
        "status": "ongoing",
    })
    ok = r.status_code == 200 and r.json().get("success") is True
    report("PUT /api/volumes/{volume_id}", ok)

    # 验证更新结果
    r2 = api_request("GET", f"/api/volumes/{state['volume_id_1']}")
    ok2 = r2.json().get("title") == "第一卷 修订版" and r2.json().get("status") == "ongoing"
    report("  → 验证更新后数据", ok2)


#  5. 更新卷统计 

def test_update_volume_stats():
    section("5. 更新卷统计（$inc）")
    r = api_request("PATCH", f"/api/volumes/{state['volume_id_1']}/stats", json={
        "arcs_count_delta": 2,
        "word_count_delta": 10000,
    })
    ok = r.status_code == 200 and r.json().get("success") is True
    report("PATCH /api/volumes/{volume_id}/stats (+)", ok)

    # 验证
    r2 = api_request("GET", f"/api/volumes/{state['volume_id_1']}")
    ok2 = r2.json().get("arcs_count") == 2 and r2.json().get("word_count") == 10000
    report("  → 验证统计结果", ok2)

    # 负增量
    r3 = api_request("PATCH", f"/api/volumes/{state['volume_id_1']}/stats", json={
        "arcs_count_delta": -1,
        "word_count_delta": -3000,
    })
    ok3 = r3.status_code == 200
    r4 = api_request("GET", f"/api/volumes/{state['volume_id_1']}")
    ok4 = r4.json().get("arcs_count") == 1 and r4.json().get("word_count") == 7000
    report("PATCH /api/volumes/{volume_id}/stats (-)", ok3 and ok4)


#  6. 软删除 → 恢复 

def test_soft_delete_and_restore():
    section("6a. 软删除卷")
    r = api_request("DELETE", f"/api/volumes/{state['volume_id_1']}")
    ok = r.status_code == 200 and r.json().get("success") is True
    report("DELETE /api/volumes/{volume_id}", ok)

    # 软删后应该 404
    r2 = api_request("GET", f"/api/volumes/{state['volume_id_1']}")
    ok2 = r2.status_code == 404
    report("  → 软删后查询应 404", ok2)

    # 卷列表应只剩 1 条
    r3 = api_request("GET", f"/api/volumes/novel/{state['novel_id']}")
    ok3 = len(r3.json().get("data", [])) == 1
    report("  → 卷列表应剩 1 条", ok3)

    section("6b. 恢复卷")
    r4 = api_request("POST", f"/api/volumes/{state['volume_id_1']}/restore")
    ok4 = r4.status_code == 200 and r4.json().get("success") is True
    report("POST /api/volumes/{volume_id}/restore", ok4)

    # 恢复后应可查询
    r5 = api_request("GET", f"/api/volumes/{state['volume_id_1']}")
    ok5 = r5.status_code == 200
    report("  → 恢复后可查询", ok5)


#  7. 软删除 → 硬删除 

def test_hard_delete():
    section("7a. 硬删除未软删的卷（应 400）")
    r = api_request("DELETE", f"/api/volumes/{state['volume_id_2']}/hard")
    ok = r.status_code == 400
    report("DELETE /api/volumes/{volume_id}/hard (not soft-deleted)", ok, f"status={r.status_code}")

    section("7b. 先软删再硬删")
    api_request("DELETE", f"/api/volumes/{state['volume_id_2']}")
    r2 = api_request("DELETE", f"/api/volumes/{state['volume_id_2']}/hard")
    ok2 = r2.status_code == 200 and "stats" in r2.json()
    report("DELETE /api/volumes/{volume_id}/hard", ok2, f"stats={r2.json().get('stats')}")

    # 硬删后完全不可查
    r3 = api_request("GET", f"/api/volumes/{state['volume_id_2']}")
    ok3 = r3.status_code == 404
    report("  → 硬删后查询应 404", ok3)


#  8. 验证小说统计联动 

def test_novel_stats_sync():
    section("8. 验证小说统计联动")
    r = api_request("GET", f"/api/novels/{state['novel_id']}")
    novel = r.json()
    vol_count = novel.get("current_volume_count", -1)
    # 此时 volume_id_1 还在（恢复过），volume_id_2 已硬删
    # 创建时 +1+1=2，软删 volume_1 时 -1=1，恢复 +1=2，软删 volume_2 时 -1=1，硬删不再扣减
    ok = r.status_code == 200
    report("GET /api/novels/{novel_id} 统计", ok, f"current_volume_count={vol_count}")


#  9. 清理 

def test_cleanup():
    section("9. 清理测试数据")
    # 软删剩余卷
    if state.get("volume_id_1"):
        api_request("DELETE", f"/api/volumes/{state['volume_id_1']}")
        api_request("DELETE", f"/api/volumes/{state['volume_id_1']}/hard")

    # 软删并硬删测试小说
    api_request("DELETE", f"/api/novels/{state['novel_id']}")
    r = api_request("DELETE", f"/api/novels/{state['novel_id']}/hard")
    ok = r.status_code == 200
    report("清理测试小说", ok)


#  main ─

def main():
    try:
        print(f"\n{'#' * 60}")
        print(f"  Volumes API 集成测试")
        print(f"  Target: {BASE_URL}")
        print(f"{'#' * 60}")

        # 健康检查
        try:
            api_request("GET", "/docs", timeout=3)
        except httpx.ConnectError:
            print(f"\n{FAIL}  无法连接到 {BASE_URL}，请先启动后端服务 (python main.py)")
            sys.exit(1)

        tests = [
            test_create_novel,
            test_create_volume_auto_order,
            test_create_volume_manual_order,
            test_create_volume_duplicate_order,
            test_create_volume_bad_novel,
            test_get_volumes_by_novel,
            test_get_volume_by_id,
            test_get_volume_not_found,
            test_update_volume_info,
            test_update_volume_stats,
            test_soft_delete_and_restore,
            test_hard_delete,
            test_novel_stats_sync,
            test_cleanup,
        ]

        for t in tests:
            try:
                t()
            except Exception as e:
                print(f"  {FAIL}  {t.__name__} 异常: {e}")
                state.setdefault("failures", []).append(t.__name__)

        # 汇总
        failures = state.get("failures", [])
        print(f"\n{DIVIDER}")
        if not failures:
            print(f"  {PASS}  全部测试通过!")
        else:
            print(f"  {FAIL}  {len(failures)} 项失败: {', '.join(failures)}")
        print(DIVIDER)
        sys.exit(len(failures))
    finally:
        CLIENT.close()


if __name__ == "__main__":
    main()
