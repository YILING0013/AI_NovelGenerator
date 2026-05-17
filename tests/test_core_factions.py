"""核心阵营生成与阵营关系 API 测试。"""

from __future__ import annotations

import pytest

from backend.api.llm_routers import create_novel_router
from backend.llm.schemas.novel_pydantic import CoreFactionsResultSchema


def _core_factions_payload() -> dict:
    """构造一份合法的核心阵营与关系请求。

    Args:
        无。

    Returns:
        可通过核心阵营 schema 校验的请求字典。
    """
    return {
        "core_factions": [
            {
                "name": "天衡宗",
                "faction_type": "宗门组织",
                "positioning": "掌控大陆正道秩序的旧势力，维持修行资源分配规则。",
                "public_stance": "公开维护修行界稳定，反对血脉滥用。",
                "core_goal": "稳住既有秩序并垄断关键传承。",
                "hidden_goal": "压制旧血脉真相重新浮出水面。",
                "resources_and_advantages": ["宗门体系", "法器库"],
                "organization_style": "层级森严，重规训与审判。",
                "core_values": ["秩序", "传承"],
                "conflict_with_mainline": "它代表主角必须冲破的既有秩序，也是主线冲突的压力来源。",
                "is_public": True,
                "influence_scope": "多区域级",
                "expandability": "可拆分出执法堂、外门派系与长老集团。",
                "tags": ["正道", "旧秩序"],
            },
            {
                "name": "归墟盟",
                "faction_type": "地下势力",
                "positioning": "由被旧秩序驱逐者组成，掌握禁术和流亡网络。",
                "public_stance": "被外界视为破坏稳定的危险联盟。",
                "core_goal": "揭开血脉真相并重写修行资源分配。",
                "hidden_goal": "利用混乱建立新的权力核心。",
                "resources_and_advantages": ["流亡网络", "禁术档案"],
                "organization_style": "松散机动，善于渗透和交易。",
                "core_values": ["复仇", "自由"],
                "conflict_with_mainline": "它推动主线真相浮现，也可能把主角拖入更激进的道路。",
                "is_public": False,
                "influence_scope": "多区域级",
                "expandability": "可扩展为情报线、黑市线与流亡者支线。",
                "tags": ["暗线", "反抗"],
            },
        ],
        "faction_relations": [
            {
                "source_faction_name": "天衡宗",
                "target_faction_name": "归墟盟",
                "relation_type": "hostile",
                "current_state": "双方公开敌对，围绕血脉真相持续清剿与反制。",
                "core_conflict": "旧秩序要掩盖真相，流亡者要撕开垄断。",
                "hidden_tension": "天衡宗内部有人暗中向归墟盟输送情报。",
                "possible_change": "敌对关系可能演变为短暂交易或内部裂变。",
                "intensity": 5,
                "is_active": True,
            },
            {
                "source_faction_name": "归墟盟",
                "target_faction_name": "天衡宗",
                "relation_type": "cold_war",
                "current_state": "双方在公开战场之外互相试探底线。",
                "core_conflict": "归墟盟需要旧秩序资源，天衡宗需要归墟盟掌握的证据。",
                "hidden_tension": "双方都有秘密合作窗口。",
                "possible_change": "后续可能出现秘密合作后再度反目。",
                "intensity": 4,
                "is_active": True,
            },
        ],
    }


def test_core_factions_schema_rejects_missing_relation_target() -> None:
    payload = _core_factions_payload()
    payload["faction_relations"][0]["target_faction_name"] = "不存在阵营"

    with pytest.raises(ValueError, match="关系目标方阵营不存在"):
        CoreFactionsResultSchema.model_validate(payload)


def test_core_factions_schema_rejects_character_extra_field() -> None:
    payload = _core_factions_payload()
    payload["core_factions"][0]["leader_character_name"] = "未创建角色"

    with pytest.raises(ValueError):
        CoreFactionsResultSchema.model_validate(payload)


def test_generate_core_factions_endpoint_with_mock_llm(client, create_novel, monkeypatch) -> None:
    novel_id = create_novel("core_factions_generate")
    expected = CoreFactionsResultSchema.model_validate(_core_factions_payload())

    class FakeLLMService:
        async def generate_structured(self, prompt, schema, **kwargs):
            """返回固定结构化核心阵营结果。"""
            assert "严禁输出角色名单" in prompt
            assert schema is CoreFactionsResultSchema
            return expected

    monkeypatch.setattr(
        create_novel_router,
        "_check_json_schema_support",
        lambda step_name, workflow_name=create_novel_router.FACTIONS_WORKFLOW_NAME: True,
    )
    monkeypatch.setattr(create_novel_router, "resolve_provider_for_step", lambda workflow, step: "fake_provider")
    monkeypatch.setattr(create_novel_router, "resolve_timeout_for_step", lambda workflow, step: None)
    monkeypatch.setattr(create_novel_router, "get_llm_service_for_step", lambda workflow, step: FakeLLMService())

    response = client.post("/api/llm/generate-core-factions", json={"novel_id": novel_id})

    assert response.status_code == 200
    assert response.json()["core_factions"][0]["name"] == "天衡宗"
    assert response.json()["faction_relations"][0]["relation_type"] == "hostile"


def test_bulk_create_core_factions_with_relations(client, create_novel) -> None:
    novel_id = create_novel("core_factions_bulk")

    response = client.post(
        f"/api/factions/novel/{novel_id}/bulk-core-with-relations",
        json=_core_factions_payload(),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert [item["faction_id"] for item in body["factions"]] == ["fac_000001", "fac_000002"]
    assert body["faction_relations"][0]["source_faction_id"] == "fac_000001"
    assert body["faction_relations"][0]["target_faction_id"] == "fac_000002"

    relations = client.get(f"/api/faction-relations/novel/{novel_id}")
    assert relations.status_code == 200
    assert len(relations.json()["data"]) == 2

    scoped_relations = client.get(f"/api/faction-relations/novel/{novel_id}/faction/fac_000001")
    assert scoped_relations.status_code == 200
    assert len(scoped_relations.json()["data"]) == 2


def test_core_faction_trash_restore_and_hard_delete_cleanup(client, create_novel) -> None:
    """核心阵营进入垃圾桶后可还原，彻底删除会清理无效关系。"""
    novel_id = create_novel("core_factions_trash")
    created = client.post(
        f"/api/factions/novel/{novel_id}/bulk-core-with-relations",
        json=_core_factions_payload(),
    )
    assert created.status_code == 200

    soft_deleted = client.delete(f"/api/factions/novel/{novel_id}/fac_000001")
    active_factions = client.get(f"/api/factions/novel/{novel_id}/level/core")
    trash = client.get(f"/api/factions/novel/{novel_id}/trash?level_type=core")
    hidden_relations = client.get(f"/api/faction-relations/novel/{novel_id}")

    assert soft_deleted.status_code == 200
    assert [item["faction_id"] for item in active_factions.json()["data"]] == ["fac_000002"]
    assert [item["faction_id"] for item in trash.json()["data"]] == ["fac_000001"]
    assert hidden_relations.json()["data"] == []

    restored = client.post(f"/api/factions/novel/{novel_id}/fac_000001/restore")
    restored_relations = client.get(f"/api/faction-relations/novel/{novel_id}")

    assert restored.status_code == 200
    assert len(restored_relations.json()["data"]) == 2

    client.delete(f"/api/factions/novel/{novel_id}/fac_000001")
    hard_deleted = client.delete(f"/api/factions/novel/{novel_id}/fac_000001/hard")
    remaining_relations = client.get(f"/api/faction-relations/novel/{novel_id}")

    assert hard_deleted.status_code == 200
    assert hard_deleted.json()["stats"]["relations_deleted"] == 2
    assert remaining_relations.json()["data"] == []


def test_generate_core_factions_rejects_existing_active_or_trash(client, create_novel) -> None:
    """已有 active 或垃圾桶核心阵营时，AI 初始化入口应拒绝重复生成。"""
    active_novel_id = create_novel("core_factions_ai_active_guard")
    active_created = client.post(
        f"/api/factions/novel/{active_novel_id}/create",
        json={"name": "已有核心阵营", "level_type": "core"},
    )
    active_response = client.post("/api/llm/generate-core-factions", json={"novel_id": active_novel_id})

    trash_novel_id = create_novel("core_factions_ai_trash_guard")
    trash_created = client.post(
        f"/api/factions/novel/{trash_novel_id}/create",
        json={"name": "垃圾桶核心阵营", "level_type": "core"},
    )
    client.delete(f"/api/factions/novel/{trash_novel_id}/{trash_created.json()['faction_id']}")
    trash_response = client.post("/api/llm/generate-core-factions", json={"novel_id": trash_novel_id})

    assert active_created.status_code == 200
    assert active_response.status_code == 409
    assert trash_created.status_code == 200
    assert trash_response.status_code == 409


def test_bulk_create_core_factions_rejects_existing_trash(client, create_novel) -> None:
    """垃圾桶中已有核心阵营时，AI 批量保存也不能重新初始化。"""
    novel_id = create_novel("core_factions_bulk_trash_guard")
    created = client.post(
        f"/api/factions/novel/{novel_id}/create",
        json={"name": "旧核心阵营", "level_type": "core"},
    )
    client.delete(f"/api/factions/novel/{novel_id}/{created.json()['faction_id']}")

    response = client.post(
        f"/api/factions/novel/{novel_id}/bulk-core-with-relations",
        json=_core_factions_payload(),
    )

    assert created.status_code == 200
    assert response.status_code == 409


def test_manual_core_faction_creation_can_exceed_six(client, create_novel) -> None:
    """手动创建核心阵营不受 AI 初始化 6 个上限限制。"""
    novel_id = create_novel("core_factions_manual_more_than_six")
    responses = [
        client.post(
            f"/api/factions/novel/{novel_id}/create",
            json={"name": f"手动核心阵营{i}", "level_type": "core"},
        )
        for i in range(7)
    ]
    listed = client.get(f"/api/factions/novel/{novel_id}/level/core")

    assert [response.status_code for response in responses] == [200] * 7
    assert len(listed.json()["data"]) == 7


def test_bulk_create_rejects_more_than_six_core_factions(client, create_novel) -> None:
    novel_id = create_novel("core_factions_too_many")
    payload = _core_factions_payload()
    payload["core_factions"] = [
        {**payload["core_factions"][0], "name": f"阵营{i}"}
        for i in range(7)
    ]
    payload["faction_relations"][0]["source_faction_name"] = "阵营0"
    payload["faction_relations"][0]["target_faction_name"] = "阵营1"
    payload["faction_relations"][1]["source_faction_name"] = "阵营1"
    payload["faction_relations"][1]["target_faction_name"] = "阵营0"

    response = client.post(
        f"/api/factions/novel/{novel_id}/bulk-core-with-relations",
        json=payload,
    )

    assert response.status_code == 422


def test_hard_delete_novel_cascades_faction_relations(client, create_novel) -> None:
    novel_id = create_novel("core_factions_cleanup")
    created = client.post(
        f"/api/factions/novel/{novel_id}/bulk-core-with-relations",
        json=_core_factions_payload(),
    )
    assert created.status_code == 200

    client.delete(f"/api/novels/{novel_id}")
    hard_deleted = client.delete(f"/api/novels/{novel_id}/hard")

    assert hard_deleted.status_code == 200
    assert hard_deleted.json()["stats"]["faction_relations_deleted"] == 2
