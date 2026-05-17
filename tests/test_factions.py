"""Factions API 的 pytest 集成测试。"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


def _create_faction(client: TestClient, novel_id: str, **overrides) -> dict:
    """创建测试阵营。

    Args:
        client: FastAPI 测试客户端。
        novel_id: 小说 ObjectId 字符串。
        **overrides: 覆盖默认请求字段。

    Returns:
        包含 status_code 和 body 的响应摘要。
    """
    payload = {
        "name": "测试阵营",
    }
    payload.update(overrides)
    response = client.post(f"/api/factions/novel/{novel_id}/create", json=payload)
    return {"status_code": response.status_code, "body": response.json()}


def _faction_path(novel_id: str, faction_id: str) -> str:
    """生成新版小说作用域阵营路径。

    Args:
        novel_id: 小说 ObjectId 字符串。
        faction_id: 业务层阵营 ID。

    Returns:
        阵营详情 API 路径。
    """
    return f"/api/factions/novel/{novel_id}/{faction_id}"


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

    detail = client.get(_faction_path(novel_id, created["body"]["faction_id"]))
    assert detail.status_code == 200
    assert detail.json()["name"] == "天衡宗"
    assert detail.json()["alias"] == []
    assert detail.json()["is_public"] is True


def test_same_faction_id_can_exist_in_different_novels(client: TestClient, create_novel):
    first_novel_id = create_novel("factions_scope_a")
    second_novel_id = create_novel("factions_scope_b")

    first = _create_faction(client, first_novel_id, faction_id="fac_shared", name="甲阵营")
    second = _create_faction(client, second_novel_id, faction_id="fac_shared", name="乙阵营")

    first_detail = client.get(_faction_path(first_novel_id, "fac_shared"))
    second_detail = client.get(_faction_path(second_novel_id, "fac_shared"))

    assert first["status_code"] == 200
    assert second["status_code"] == 200
    assert first_detail.json()["name"] == "甲阵营"
    assert second_detail.json()["name"] == "乙阵营"


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


def test_duplicate_faction_id_conflict_in_same_novel(client: TestClient, create_novel):
    novel_id = create_novel("factions_duplicate")
    first = _create_faction(client, novel_id, faction_id="fac_custom_duplicate", name="甲阵营")
    duplicate = _create_faction(client, novel_id, faction_id="fac_custom_duplicate", name="乙阵营")

    assert first["status_code"] == 200
    assert duplicate["status_code"] == 409


def test_create_faction_bad_novel(client: TestClient):
    response = client.post(
        "/api/factions/novel/000000000000000000000000/create",
        json={
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


def test_get_faction_by_scoped_id_and_not_found(client: TestClient, create_novel):
    novel_id = create_novel("factions_detail")
    created = _create_faction(client, novel_id, name="天衡宗")

    found = client.get(_faction_path(novel_id, created["body"]["faction_id"]))
    missing = client.get(_faction_path(novel_id, "fac_not_exists"))

    assert found.status_code == 200
    assert found.json()["name"] == "天衡宗"
    assert missing.status_code == 404


def test_old_unscoped_faction_routes_are_removed(client: TestClient, create_novel):
    novel_id = create_novel("factions_removed_routes")
    created = _create_faction(client, novel_id, name="天衡宗")

    removed_detail = client.get(f"/api/factions/{created['body']['faction_id']}")
    removed_create = client.post("/api/factions/create", json={"novel_id": novel_id, "name": "旧接口"})

    assert removed_detail.status_code == 404
    assert removed_create.status_code == 404


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
        _faction_path(novel_id, faction_id),
        json={
            "name": "天衡宗修订版",
            "alias": ["天衡", "衡宗"],
            "tags": ["核心势力", "正道"],
            "extra": {"symbol": "天衡剑印"},
        },
    )
    detail = client.get(_faction_path(novel_id, faction_id))

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
        f"/api/factions/novel/{novel_id}/batch-sort",
        json={
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


def test_soft_delete_parent_unlinks_only_same_novel_children_and_restore(client: TestClient, create_novel):
    first_novel_id = create_novel("factions_restore_a")
    second_novel_id = create_novel("factions_restore_b")
    parent = _create_faction(client, first_novel_id, faction_id="fac_parent", name="天衡宗")
    child = _create_faction(
        client,
        first_novel_id,
        name="执法堂",
        parent_faction_id=parent["body"]["faction_id"],
    )
    other_parent = _create_faction(client, second_novel_id, faction_id="fac_parent", name="另一本父阵营")
    other_child = _create_faction(
        client,
        second_novel_id,
        name="另一本子阵营",
        parent_faction_id=other_parent["body"]["faction_id"],
    )

    deleted = client.delete(_faction_path(first_novel_id, parent["body"]["faction_id"]))
    missing = client.get(_faction_path(first_novel_id, parent["body"]["faction_id"]))
    child_detail = client.get(_faction_path(first_novel_id, child["body"]["faction_id"]))
    other_child_detail = client.get(_faction_path(second_novel_id, other_child["body"]["faction_id"]))
    restored = client.post(f"{_faction_path(first_novel_id, parent['body']['faction_id'])}/restore")
    restored_detail = client.get(_faction_path(first_novel_id, parent["body"]["faction_id"]))

    assert deleted.status_code == 200
    assert deleted.json()["success"] is True
    assert missing.status_code == 404
    assert child_detail.status_code == 200
    assert child_detail.json()["parent_faction_id"] is None
    assert other_child_detail.status_code == 200
    assert other_child_detail.json()["parent_faction_id"] == "fac_parent"
    assert restored.status_code == 200
    assert restored.json()["success"] is True
    assert restored_detail.status_code == 200


def test_soft_delete_then_recreate_same_faction_id_and_restore_conflict(client: TestClient, create_novel):
    novel_id = create_novel("factions_partial_unique")
    original = _create_faction(client, novel_id, faction_id="fac_reusable", name="原阵营")

    deleted = client.delete(_faction_path(novel_id, original["body"]["faction_id"]))
    recreated = _create_faction(client, novel_id, faction_id="fac_reusable", name="新阵营")
    restore_conflict = client.post(f"{_faction_path(novel_id, original['body']['faction_id'])}/restore")

    assert deleted.status_code == 200
    assert recreated["status_code"] == 200
    assert restore_conflict.status_code == 409


def test_hard_delete_requires_soft_delete(client: TestClient, create_novel):
    novel_id = create_novel("factions_hard_guard")
    created = _create_faction(client, novel_id, name="四海商盟")

    rejected = client.delete(f"{_faction_path(novel_id, created['body']['faction_id'])}/hard")

    assert rejected.status_code == 400


def test_hard_delete_faction_after_soft_delete(client: TestClient, create_novel):
    novel_id = create_novel("factions_hard")
    created = _create_faction(client, novel_id, name="四海商盟")
    faction_id = created["body"]["faction_id"]

    client.delete(_faction_path(novel_id, faction_id))
    deleted = client.delete(f"{_faction_path(novel_id, faction_id)}/hard")
    missing = client.get(_faction_path(novel_id, faction_id))

    assert deleted.status_code == 200
    assert deleted.json()["stats"]["faction_deleted"] == 1
    assert missing.status_code == 404


def test_hard_delete_novel_cascades_factions(client: TestClient, create_novel):
    novel_id = create_novel("factions_novel_cleanup")
    created = _create_faction(client, novel_id, name="随小说删除的阵营")
    faction_id = created["body"]["faction_id"]

    soft_deleted = client.delete(f"/api/novels/{novel_id}")
    hard_deleted = client.delete(f"/api/novels/{novel_id}/hard")
    missing = client.get(_faction_path(novel_id, faction_id))

    assert soft_deleted.status_code == 200
    assert hard_deleted.status_code == 200
    assert hard_deleted.json()["stats"]["factions_deleted"] == 1
    assert missing.status_code == 404


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
