import asyncio
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.api.error_protocol import DomainApiError
from backend.config.config import (
    ConfigCommitError,
    ConfigVersionConflictError,
    capture_config_snapshot,
    get_all_config,
    get_config_read_model,
    project_config_for_read,
    restore_config_snapshot,
    update_config,
    validate_provider_alias,
)
from backend.db.mongo import connect_to_mongo
from backend.llm.config import LLMProviderType, LLMApiMode, StructuredOutputMode
from backend.llm.generation_options import ReasoningOptions
from backend.services.llm.provider_test_service import (
    ProviderTestRequest,
    ProviderTestResponse,
    test_llm_provider_capabilities,
)
from backend.services.task_flows import store as task_flow_store
from backend.services.task_flows.provider_references import (
    ProviderReferencedError,
    update_flow_provider_references,
)

router = APIRouter(prefix="/api/config", tags=["config"])

# 配置文件、运行缓存和 Mongo 连接必须作为同一个进程内提交边界串行切换。
_config_update_lock = asyncio.Lock()


class SecretUpdateRequest(BaseModel):
    """描述浏览器对受保护配置值的显式操作。"""

    model_config = ConfigDict(extra="forbid", strict=True)

    action: Literal["preserve", "replace", "clear"] = "preserve"
    value: str | None = None

    @model_validator(mode="after")
    def validate_value(self) -> "SecretUpdateRequest":
        """校验密钥动作和值的组合，避免占位符或空替换进入服务层。

        Args:
            无。

        Returns:
            已通过动作语义校验的请求对象。
        """
        if self.action == "replace" and not (self.value and self.value.strip()):
            raise ValueError("replace 动作必须携带非空密钥值")
        if self.action != "replace" and self.value not in (None, ""):
            raise ValueError(f"{self.action} 动作不能携带密钥值")
        return self


class ProviderConfigPatch(ReasoningOptions):
    """设置工作台允许提交的单个 Provider 字段。"""

    model_config = ConfigDict(extra="forbid", strict=True)

    type: LLMProviderType | None = None
    api_mode: LLMApiMode | None = None
    structured_output_mode: StructuredOutputMode | None = None
    base_url: str | None = None
    api_key_update: SecretUpdateRequest | None = None
    default_model: str | None = None
    enabled: bool | None = None
    timeout_seconds: int | None = Field(default=None, gt=0)
    max_retries: int | None = Field(default=None, ge=0)
    max_concurrency: int | None = Field(default=None, gt=0)
    use_system_proxy: bool | None = None
    supports_streaming: bool | None = None
    supports_json_schema: bool | None = None
    supports_json_output: bool | None = None
    supports_function_calling: bool | None = None
    # 模型或接口资料，只校验数值，不改变任何请求预算。
    context_window_tokens: int | None = Field(default=None, gt=0, le=9007199254740991, strict=True, description="上下文总容量，未知留空")
    input_token_limit: int | None = Field(default=None, gt=0, le=9007199254740991, strict=True, description="单次输入上限，未知留空")
    output_token_limit: int | None = Field(default=None, gt=0, le=9007199254740991, strict=True, description="模型或接口输出上限，未知留空")

    temperature: float | None = Field(default=None, ge=0, le=2)
    top_p: float | None = Field(default=None, ge=0, le=1)
    max_tokens: int | None = Field(default=None, gt=0)
    system_prompt: str | None = None
    presence_penalty: float | None = Field(default=None, ge=-2, le=2)
    frequency_penalty: float | None = Field(default=None, ge=-2, le=2)

    @field_validator("system_prompt")
    @classmethod
    def normalize_system_prompt(cls, value: str | None) -> str | None:
        """把全空白系统提示词归一为未配置，其余内容保持原样。

        Args:
            value: 浏览器提交的系统提示词。

        Returns:
            ``None`` 或保持原样的非空白提示词。
        """
        if isinstance(value, str) and not value.strip():
            return None
        return value


class LLMConfigPatch(BaseModel):
    """设置工作台允许提交的 LLM 配置字段。"""

    model_config = ConfigDict(extra="forbid", strict=True)

    default_provider: str | None = None
    format_review_provider: str | None = None
    providers: dict[str, ProviderConfigPatch] | None = None


class ProviderRenameRequest(BaseModel):
    """Provider 别名重命名操作。"""

    model_config = ConfigDict(extra="forbid", populate_by_name=True, strict=True)

    source: str = Field(alias="from")
    target: str = Field(alias="to")

    _validate_aliases = field_validator("source", "target")(validate_provider_alias)


class ConfigPatch(BaseModel):
    """设置工作台可修改的根配置字段白名单。"""

    model_config = ConfigDict(extra="forbid", strict=True)

    mongodb_url_update: SecretUpdateRequest | None = None
    mongo_database_name: str | None = Field(default=None, min_length=1)
    mongo_timeout_ms: int | None = Field(default=None, gt=0)
    mongo_transaction_mode: Literal["auto", "required", "disabled"] | None = None
    llm: LLMConfigPatch | None = None
    provider_renames: list[ProviderRenameRequest] | None = Field(
        default=None,
        alias="_provider_renames",
    )


class ConfigUpdateRequest(BaseModel):
    """严格包裹设置工作台的配置 patch 与 CAS 版本。"""

    model_config = ConfigDict(extra="forbid", strict=True)

    expected_config_version: int = Field(ge=1)
    patch: ConfigPatch


@router.get("")
async def get_configurations():
    """获取当前生效的项目配置。

    Args:
        无。

    Returns:
        Mongo URI 与 Provider 密钥已脱敏、系统提示词可直接读取的配置投影。
    """
    # 读取也等待正在进行的依赖切换，避免浏览器观察到稍后将回滚的暂存版本。
    async with _config_update_lock:
        return {"data": get_config_read_model()}


@router.put("")
async def update_configurations(request: ConfigUpdateRequest):
    """原子更新项目配置，并在依赖刷新失败时恢复旧版本。

    Args:
        request: 包含浏览器读取版本与严格配置 patch 的请求。

    Returns:
        保存后的配置投影；Mongo URI 与 Provider 密钥脱敏，系统提示词直接返回。
    """
    async with _config_update_lock:
        previous_snapshot = capture_config_snapshot()
        try:
            try:
                updated_config = update_config(
                    request.patch.model_dump(by_alias=True, exclude_unset=True),
                    expected_config_version=request.expected_config_version,
                )
            except ConfigVersionConflictError as exc:
                raise DomainApiError(
                    "CONFIG_VERSION_CONFLICT",
                    str(exc),
                    status_code=409,
                ) from exc
            except ValueError as exc:
                raise DomainApiError("INVALID_CONFIG", str(exc), status_code=422) from exc
            except ConfigCommitError as exc:
                raise DomainApiError(
                    "CONFIG_COMMIT_FAILED",
                    "配置提交失败，旧配置已恢复；请检查服务日志后重试",
                    status_code=503,
                ) from exc

            await connect_to_mongo()
            previous_aliases = set(previous_snapshot.effective_config.get("llm", {}).get("providers", {}))
            current_aliases = set(updated_config.get("llm", {}).get("providers", {}))
            renames = [(item.source, item.target) for item in request.patch.provider_renames or []]
            flow_updates = []
            if renames or previous_aliases - current_aliases:
                # 等连接切换成功再发布方案，文件锁内不跨 await，避免阻塞其他图编辑请求。
                flow_updates = update_flow_provider_references(
                    task_flow_store.flow_store(), previous_aliases, current_aliases, renames,
                )
            return {
                "message": "Config updated",
                "data": project_config_for_read(updated_config),
                "task_flow_updates": [reference.model_dump() for reference in flow_updates],
            }
        except DomainApiError:
            raise
        except Exception as exc:
            try:
                restore_config_snapshot(previous_snapshot)
                # connect_to_mongo 采用成功后切换；此处确保恢复配置对应的连接可用。
                await connect_to_mongo()
            except Exception as restore_exc:
                raise DomainApiError(
                    "CONFIG_ROLLBACK_FAILED",
                    "配置依赖刷新失败，且旧版本恢复失败；请检查服务日志",
                    status_code=503,
                ) from restore_exc
            if isinstance(exc, ProviderReferencedError):
                raise DomainApiError(
                    "PROVIDER_REFERENCED_BY_TASK_FLOW",
                    str(exc),
                    status_code=409,
                    details={"references": exc.references},
                ) from exc
            raise DomainApiError(
                "CONFIG_DEPENDENCY_UNAVAILABLE",
                "配置依赖刷新失败，已恢复旧配置",
                status_code=503,
            ) from exc


@router.post("/llm-providers/test", response_model=ProviderTestResponse)
async def test_llm_provider(request: ProviderTestRequest):
    """测试当前表单中的 LLM Provider 接口能力，不写入配置文件。

    Args:
        request: 前端提交的 Provider 别名与当前表单配置。

    Returns:
        接口可用性、流式、JSON Schema 和 Function Calling 测试结果。
    """
    try:
        effective_request = request
        if request.use_stored_api_key:
            stored_provider = (
                get_all_config(force_reload=True)
                .get("llm", {})
                .get("providers", {})
                .get(request.alias, {})
            )
            stored_api_key = stored_provider.get("api_key") if isinstance(stored_provider, dict) else None
            if not isinstance(stored_api_key, str) or not stored_api_key.strip():
                raise DomainApiError(
                    "PROVIDER_SECRET_NOT_CONFIGURED",
                    "所选 Provider 没有已保存的 API Key",
                    status_code=422,
                )
            # 已保存密钥只在本次内存探测对象中注入，不进入响应或浏览器状态。
            effective_request = request.model_copy(
                update={
                    "provider": request.provider.model_copy(update={"api_key": stored_api_key}),
                    "use_stored_api_key": False,
                }
            )
        return await test_llm_provider_capabilities(effective_request)
    except DomainApiError:
        raise
    except Exception as exc:
        raise DomainApiError(
            "PROVIDER_TEST_FAILED",
            "Provider 能力测试失败，请检查当前表单与服务端日志",
            status_code=503,
        ) from exc
