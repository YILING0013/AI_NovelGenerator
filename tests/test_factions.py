"""Factions API 的 pytest 集成测试。"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


def _create_faction(client: TestClient, novel_id: str, **overrides) -> dict:
    payload = {
        "novel_id": novel_id,
        "name": "测试阵营",
    }
    payload.update(overrides)
    response = client.post("/api/factions/create", json=payload)
    return {"status_code": response.status_code, "body": response.json()}


def test_create_faction_auto_id_and_defaults(client: TestClient, create_novel):
    novel_id = create_novel("factions_auto")

    created = _create_faction(
        client,
        novel_id,
        name="天衡宗",
        faction_type="宗门组织",
        level_type="core",
        sort_order=10,
        core_goal="维持修行界秩序",
    )

    assert created["status_code"] == 200
    assert created["body"]["faction_id"] == "fac_000001"

    detail = client.get(f"/api/factions/{created['body']['faction_id']}")
    assert detail.status_code == 200
    assert detail.json()["name"] == "天衡宗"
    assert detail.json()["alias"] == []
    assert detail.json()["is_public"] is True


def test_create_child_faction_and_get_children(client: TestClient, create_novel):
    novel_id = create_novel("factions_children")
    parent = _create_faction(client, novel_id, name="天衡宗")
    child = _create_faction(
        client,
        novel_id,
        name="天衡宗执法堂",
        level_type="functional",
        parent_faction_id=parent["body"]["faction_id"],
        sort_order=20,
    )

    children = client.get(
        f"/api/factions/novel/{novel_id}/children/{parent['body']['faction_id']}"
    )

    assert parent["status_code"] == 200
    assert child["status_code"] == 200
    assert children.status_code == 200
    assert len(children.json()["data"]) == 1
    assert children.json()["data"][0]["faction_id"] == child["body"]["faction_id"]


def test_duplicate_faction_id_conflict(client: TestClient, create_novel):
    novel_id = create_novel("factions_duplicate")
    first = _create_faction(client, novel_id, faction_id="fac_custom_duplicate", name="甲阵营")
    duplicate = _create_faction(client, novel_id, faction_id="fac_custom_duplicate", name="乙阵营")

    assert first["status_code"] == 200
    assert duplicate["status_code"] == 409


def test_create_faction_bad_novel(client: TestClient):
    response = client.post(
        "/api/factions/create",
        json={
            "novel_id": "000000000000000000000000",
            "name": "孤儿阵营",
        },
    )

    assert response.status_code == 404


def test_get_factions_by_novel_sorted(client: TestClient, create_novel):
    novel_id = create_novel("factions_sorted")
    first = _create_faction(client, novel_id, name="第一阵营", sort_order=30)
    second = _create_faction(client, novel_id, name="第二阵营", sort_order=10)
    third = _create_faction(client, novel_id, name="第三阵营", sort_order=20)

    listed = client.get(f"/api/factions/novel/{novel_id}")
    data = listed.json()["data"]

    assert first["status_code"] == 200
    assert second["status_code"] == 200
    assert third["status_code"] == 200
    assert listed.status_code == 200
    assert [item["sort_order"] for item in data] == [10, 20, 30]


def test_get_faction_by_id_and_not_found(client: TestClient, create_novel):
    novel_id = create_novel("factions_detail")
    created = _create_faction(client, novel_id, name="天衡宗")

    found = client.get(f"/api/factions/{created['body']['faction_id']}")
    missing = client.get("/api/factions/fac_not_exists")

    assert found.status_code == 200
    assert found.json()["name"] == "天衡宗"
    assert missing.status_code == 404


def test_get_factions_by_level_type(client: TestClient, create_novel):
    novel_id = create_novel("factions_level")
    _create_faction(client, novel_id, name="核心阵营", level_type="core")
    child = _create_faction(client, novel_id, name="执法堂", level_type="functional")

    response = client.get(f"/api/factions/novel/{novel_id}/level/functional")
    data = response.json()["data"]

    assert response.status_code == 200
    assert len(data) == 1
    assert data[0]["faction_id"] == child["body"]["faction_id"]


def test_update_faction_info(client: TestClient, create_novel):
    novel_id = create_novel("factions_update")
    created = _create_faction(client, novel_id, name="旧名")
    faction_id = created["body"]["faction_id"]

    updated = client.put(
        f"/api/factions/{faction_id}",
        json={
            "name": "天衡宗修订版",
            "alias": ["天衡", "衡宗"],
            "tags": ["核心势力", "正道"],
            "extra": {"symbol": "天衡剑印"},
        },
    )
    detail = client.get(f"/api/factions/{faction_id}")

    assert updated.status_code == 200
    assert updated.json()["success"] is True
    assert detail.json()["name"] == "天衡宗修订版"
    assert detail.json()["alias"] == ["天衡", "衡宗"]
    assert detail.json()["extra"]["symbol"] == "天衡剑印"


def test_batch_update_sort_order(client: TestClient, create_novel):
    novel_id = create_novel("factions_sort")
    first = _create_faction(client, novel_id, name="甲", sort_order=30)
    second = _create_faction(client, novel_id, name="乙", sort_order=10)
    third = _create_faction(client, novel_id, name="丙", sort_order=20)

    updated = client.patch(
        "/api/factions/batch-sort",
        json={
            "novel_id": novel_id,
            "sort_map": {
                first["body"]["faction_id"]: 20,
                second["body"]["faction_id"]: 30,
                third["body"]["faction_id"]: 10,
            },
        },
    )
    listed = client.get(f"/api/factions/novel/{novel_id}")

    assert updated.status_code == 200
    assert updated.json()["updated_count"] == 3
    assert [item["faction_id"] for item in listed.json()["data"]] == [
        third["body"]["faction_id"],
        first["body"]["faction_id"],
        second["body"]["faction_id"],
    ]


def test_soft_delete_parent_unlinks_children_and_restore(client: TestClient, create_novel):
    novel_id = create_novel("factions_restore")
    parent = _create_faction(client, novel_id, name="天衡宗")
    child = _create_faction(
        client,
        novel_id,
        name="执法堂",
        parent_faction_id=parent["body"]["faction_id"],
    )

    deleted = client.delete(f"/api/factions/{parent['body']['faction_id']}")
    missing = client.get(f"/api/factions/{parent['body']['faction_id']}")
    child_detail = client.get(f"/api/factions/{child['body']['faction_id']}")
    restored = client.post(f"/api/factions/{parent['body']['faction_id']}/restore")
    restored_detail = client.get(f"/api/factions/{parent['body']['faction_id']}")

    assert deleted.status_code == 200
    assert deleted.json()["success"] is True
    assert missing.status_code == 404
    assert child_detail.status_code == 200
    assert child_detail.json()["parent_faction_id"] is None
    assert restored.status_code == 200
    assert restored.json()["success"] is True
    assert restored_detail.status_code == 200


def test_hard_delete_requires_soft_delete(client: TestClient, create_novel):
    novel_id = create_novel("factions_hard_guard")
    created = _create_faction(client, novel_id, name="四海商盟")

    rejected = client.delete(f"/api/factions/{created['body']['faction_id']}/hard")

    assert rejected.status_code == 400


def test_hard_delete_faction_after_soft_delete(client: TestClient, create_novel):
    novel_id = create_novel("factions_hard")
    created = _create_faction(client, novel_id, name="四海商盟")
    faction_id = created["body"]["faction_id"]

    client.delete(f"/api/factions/{faction_id}")
    deleted = client.delete(f"/api/factions/{faction_id}/hard")
    missing = client.get(f"/api/factions/{faction_id}")

    assert deleted.status_code == 200
    assert deleted.json()["stats"]["faction_deleted"] == 1
    assert missing.status_code == 404


def test_hard_delete_novel_cascades_factions(client: TestClient, create_novel):
    novel_id = create_novel("factions_novel_cleanup")
    created = _create_faction(client, novel_id, name="随小说删除的阵营")
    faction_id = created["body"]["faction_id"]

    soft_deleted = client.delete(f"/api/novels/{novel_id}")
    hard_deleted = client.delete(f"/api/novels/{novel_id}/hard")
    missing = client.get(f"/api/factions/{faction_id}")

    assert soft_deleted.status_code == 200
    assert hard_deleted.status_code == 200
    assert hard_deleted.json()["stats"]["factions_deleted"] == 1
    assert missing.status_code == 404


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))