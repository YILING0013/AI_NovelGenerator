"""Volumes API 的 pytest 集成测试。"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


def _create_volume(client: TestClient, novel_id: str, **overrides) -> dict:
    payload = {
        "novel_id": novel_id,
        "title": "测试卷",
    }
    payload.update(overrides)
    response = client.post("/api/volumes/create", json=payload)
    return {"status_code": response.status_code, "body": response.json()}


def test_create_volume_auto_order(client: TestClient, create_novel):
    novel_id = create_novel("volumes_auto")

    created = _create_volume(
        client,
        novel_id,
        title="第一卷 测试卷",
        summary="这是自动序号的测试卷",
    )

    assert created["status_code"] == 200
    volume_id = created["body"]["id"]

    detail = client.get(f"/api/volumes/{volume_id}")
    assert detail.status_code == 200
    assert detail.json()["title"] == "第一卷 测试卷"
    assert detail.json()["order_index"] == 1


def test_create_volume_manual_order_and_duplicate(client: TestClient, create_novel):
    novel_id = create_novel("volumes_manual")

    first = _create_volume(client, novel_id, title="第五卷 跳跃序号", order_index=5)
    duplicate = _create_volume(client, novel_id, title="重复序号卷", order_index=5)

    assert first["status_code"] == 200
    assert duplicate["status_code"] == 409


def test_create_volume_bad_novel(client: TestClient):
    response = client.post(
        "/api/volumes/create",
        json={
            "novel_id": "000000000000000000000000",
            "title": "孤儿卷",
        },
    )

    assert response.status_code == 404


def test_get_volumes_by_novel_sorted(client: TestClient, create_novel):
    novel_id = create_novel("volumes_list")
    _create_volume(client, novel_id, title="第一卷", summary="auto")
    _create_volume(client, novel_id, title="第五卷", order_index=5)

    response = client.get(f"/api/volumes/novel/{novel_id}")
    data = response.json()["data"]

    assert response.status_code == 200
    assert len(data) == 2
    assert [item["order_index"] for item in data] == [1, 5]


def test_get_volume_by_id_and_not_found(client: TestClient, create_novel):
    novel_id = create_novel("volumes_detail")
    created = _create_volume(client, novel_id, title="第一卷 测试卷")
    volume_id = created["body"]["id"]

    found = client.get(f"/api/volumes/{volume_id}")
    missing = client.get("/api/volumes/000000000000000000000000")

    assert found.status_code == 200
    assert found.json()["title"] == "第一卷 测试卷"
    assert missing.status_code == 404


def test_update_volume_info(client: TestClient, create_novel):
    novel_id = create_novel("volumes_update")
    created = _create_volume(client, novel_id, title="旧标题")
    volume_id = created["body"]["id"]

    updated = client.put(
        f"/api/volumes/{volume_id}",
        json={
            "title": "第一卷 修订版",
            "status": "ongoing",
        },
    )
    detail = client.get(f"/api/volumes/{volume_id}")

    assert updated.status_code == 200
    assert updated.json()["success"] is True
    assert detail.json()["title"] == "第一卷 修订版"
    assert detail.json()["status"] == "ongoing"


def test_update_volume_stats(client: TestClient, create_novel):
    novel_id = create_novel("volumes_stats")
    created = _create_volume(client, novel_id, title="统计卷")
    volume_id = created["body"]["id"]

    increased = client.patch(
        f"/api/volumes/{volume_id}/stats",
        json={
            "arcs_count_delta": 2,
            "word_count_delta": 10000,
        },
    )
    decreased = client.patch(
        f"/api/volumes/{volume_id}/stats",
        json={
            "arcs_count_delta": -1,
            "word_count_delta": -3000,
        },
    )
    detail = client.get(f"/api/volumes/{volume_id}")

    assert increased.status_code == 200
    assert increased.json()["success"] is True
    assert decreased.status_code == 200
    assert detail.json()["arcs_count"] == 1
    assert detail.json()["word_count"] == 7000


def test_soft_delete_and_restore_volume(client: TestClient, create_novel):
    novel_id = create_novel("volumes_restore")
    first = _create_volume(client, novel_id, title="第一卷")
    second = _create_volume(client, novel_id, title="第二卷")
    volume_id = first["body"]["id"]

    deleted = client.delete(f"/api/volumes/{volume_id}")
    missing = client.get(f"/api/volumes/{volume_id}")
    listed = client.get(f"/api/volumes/novel/{novel_id}")
    restored = client.post(f"/api/volumes/{volume_id}/restore")
    restored_detail = client.get(f"/api/volumes/{volume_id}")

    assert second["status_code"] == 200
    assert deleted.status_code == 200
    assert deleted.json()["success"] is True
    assert missing.status_code == 404
    assert len(listed.json()["data"]) == 1
    assert restored.status_code == 200
    assert restored.json()["success"] is True
    assert restored_detail.status_code == 200


def test_hard_delete_volume(client: TestClient, create_novel):
    novel_id = create_novel("volumes_hard_delete")
    created = _create_volume(client, novel_id, title="待硬删卷")
    volume_id = created["body"]["id"]

    rejected = client.delete(f"/api/volumes/{volume_id}/hard")
    soft_deleted = client.delete(f"/api/volumes/{volume_id}")
    hard_deleted = client.delete(f"/api/volumes/{volume_id}/hard")
    missing = client.get(f"/api/volumes/{volume_id}")

    assert rejected.status_code == 400
    assert soft_deleted.status_code == 200
    assert hard_deleted.status_code == 200
    assert hard_deleted.json()["stats"]["volume_deleted"] == 1
    assert missing.status_code == 404


def test_novel_stats_sync_for_volume_count(client: TestClient, create_novel):
    novel_id = create_novel("volumes_stats_sync")
    first = _create_volume(client, novel_id, title="第一卷")
    second = _create_volume(client, novel_id, title="第二卷")

    novel = client.get(f"/api/novels/{novel_id}")
    assert novel.status_code == 200
    assert novel.json()["current_volume_count"] == 2

    volume_id = second["body"]["id"]
    client.delete(f"/api/volumes/{volume_id}")
    after_delete = client.get(f"/api/novels/{novel_id}")
    client.post(f"/api/volumes/{volume_id}/restore")
    after_restore = client.get(f"/api/novels/{novel_id}")

    assert first["status_code"] == 200
    assert after_delete.json()["current_volume_count"] == 1
    assert after_restore.json()["current_volume_count"] == 2


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
