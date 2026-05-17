from typing import Any, Dict

from fastapi import APIRouter, HTTPException

from backend.config.config import get_all_config, update_config
from backend.db.mongo import connect_to_mongo
from backend.services.llm.provider_test_service import (
    ProviderTestRequest,
    ProviderTestResponse,
    test_llm_provider_capabilities,
)

router = APIRouter(prefix="/api/config", tags=["config"])


@router.get("")
async def get_configurations():
    """获取当前生效的全部项目配置。"""
    return {"data": get_all_config()}


@router.put("")
async def update_configurations(config_data: Dict[str, Any]):
    """更新项目配置，并在需要时刷新Mongo连接。"""
    try:
        updated_config = update_config(config_data)
        await connect_to_mongo()
        return {"message": "Config updated", "data": updated_config}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/llm-providers/test", response_model=ProviderTestResponse)
async def test_llm_provider(request: ProviderTestRequest):
    """测试当前表单中的 LLM Provider 接口能力，不写入配置文件。

    Args:
        request: 前端提交的 Provider 别名与当前表单配置。

    Returns:
        接口可用性、流式、JSON Schema 和 Function Calling 测试结果。
    """
    try:
        return await test_llm_provider_capabilities(request)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
