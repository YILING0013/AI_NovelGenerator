from typing import Any, Dict

from fastapi import APIRouter, HTTPException

from application.config.config import get_all_config, update_config
from application.db.mongo import connect_to_mongo

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