"""AI 浏览器本地候选的依据、确认信封与失效校验契约。"""

from __future__ import annotations

from hashlib import sha256
import json
from typing import Annotated, Any, Mapping

from pydantic import Field, model_validator

from backend.api.contracts import StrictRequestModel, StrictResponseModel
from backend.api.error_protocol import DomainApiError
from backend.db.write_contracts import IDEMPOTENCY_KEY_RE


CandidateIdempotencyKey = Annotated[
    str,
    Field(
        min_length=16,
        max_length=128,
        pattern=IDEMPOTENCY_KEY_RE.pattern,
        description="Idempotency-Key request header mà giao diện xác nhận miền yêu cầu",
    ),
]

# 当前合法峰值约为 1401；预留演进空间但保持明确的请求体上界。
MAX_CANDIDATE_SOURCE_REFS = 2000


class CandidateSourceRefV1(StrictRequestModel):
    "Một tham chiếu sự kiện chính thức được đọc khi sinh ứng viên."

    resource_type: str = Field(pattern=r"^[a-z][a-z0-9_]{1,63}$")
    id: str = Field(min_length=1, max_length=100)
    version: int = Field(ge=1)


class CandidateBasisV1(StrictRequestModel):
    "Căn cứ có thể tính lại cho ứng viên liên kết và đầu vào sinh."

    novel_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{24}$")
    workflow: str = Field(pattern=r"^[a-z][a-z0-9_]{2,127}$")
    step: str = Field(pattern=r"^[a-z][a-z0-9_]{1,127}$")
    schema_id: str = Field(pattern=r"^[a-z][a-z0-9_.-]{2,127}$")
    schema_version: int = Field(ge=1)
    input_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_refs: list[CandidateSourceRefV1] = Field(
        max_length=MAX_CANDIDATE_SOURCE_REFS
    )
    # 图版本与生成配置属于候选依据，不改变原业务的 workflow/step 标识。
    flow_ref: dict[str, Any]
    flow_snapshot: dict[str, Any]

    @model_validator(mode="after")
    def validate_unique_source_refs(self) -> "CandidateBasisV1":
        """拒绝同一个正式资源在依据中出现多个版本。

        Args:
            无。

        Returns:
            来源引用唯一的候选依据。
        """
        identities = [(item.resource_type, item.id) for item in self.source_refs]
        if len(identities) != len(set(identities)):
            raise ValueError("source_refs không được tham chiếu trùng cùng một tài nguyên")
        from backend.services.task_flows.contracts import FlowRef

        FlowRef.model_validate(self.flow_ref)
        if self.flow_snapshot.get("flow_ref") != self.flow_ref:
            raise ValueError("Phương án sửa đổi không nhất quán với ảnh chụp nhanh của lần sinh")
        if not all(isinstance(self.flow_snapshot.get(key), dict) for key in ("scope", "business_input", "flow_inputs", "execution")):
            raise ValueError("Ảnh chụp nhanh sinh quy trình thiếu đầu vào thiết yếu")
        definition_hash = self.flow_snapshot.get("definition_hash", "")
        if not isinstance(definition_hash, str) or len(definition_hash) != 64 or any(c not in "0123456789abcdef" for c in definition_hash):
            raise ValueError("Dấu vết định nghĩa quy trình không hợp lệ")
        if self.flow_snapshot["scope"].get("novel_id") != self.novel_id:
            raise ValueError("Vị trí thao tác quy trình không nhất quán với tiểu thuyết ứng viên")
        if self.novel_id is None:
            if self.workflow not in {
                "create_novel_by_ai",
                "rewrite_novel_field_by_ai",
            }:
                raise ValueError("Chỉ ứng viên sách mới do AI tạo hoặc ứng viên trường ở trạng thái chưa tạo cho phép novel_id trống")
            if self.source_refs:
                raise ValueError("Ứng viên tiểu thuyết chưa lưu không được tham chiếu tài nguyên chính thức chưa tồn tại")
        return self


class CandidateConfirmationEnvelopeV1(StrictRequestModel):
    "Vỏ gửi ứng viên tái sử dụng bởi giao diện xác nhận theo miền."

    candidate: dict[str, Any] = Field(min_length=1)
    basis: CandidateBasisV1
    expected_versions: dict[str, int] = Field(
        max_length=MAX_CANDIDATE_SOURCE_REFS
    )

    @model_validator(mode="after")
    def validate_expected_versions(self) -> "CandidateConfirmationEnvelopeV1":
        """确保确认版本键值非空且为正整数。

        Args:
            无。

        Returns:
            版本映射可用于领域 CAS 校验的确认信封。
        """
        if any(not key.strip() or isinstance(value, bool) or value < 1 for key, value in self.expected_versions.items()):
            raise ValueError("expected_versions phải dùng khóa tài nguyên khác rỗng và phiên bản là số nguyên dương")
        if self.basis.novel_id is None:
            if self.expected_versions:
                raise ValueError("Xác nhận sách mới AI không được kèm phiên bản tài nguyên chính thức chưa tồn tại")
        elif not self.expected_versions:
            raise ValueError("Xác nhận ứng viên miền đã lưu phải kèm expected_versions")
        return self


class CandidateGenerationEnvelopeV1(StrictResponseModel):
    "Bao ứng viên dùng chung cho phản hồi thường và ``done.result`` của SSE."

    workflow: str = Field(pattern=r"^[a-z][a-z0-9_]{2,127}$")
    step: str = Field(pattern=r"^[a-z][a-z0-9_]{1,127}$")
    schema_id: str = Field(pattern=r"^[a-z][a-z0-9_.-]{2,127}$")
    schema_version: int = Field(ge=1)
    candidate: dict[str, Any] = Field(min_length=1)
    basis: CandidateBasisV1

    @model_validator(mode="after")
    def validate_matches_basis(self) -> "CandidateGenerationEnvelopeV1":
        """确保公开信封与 basis 使用同一工作流及 Schema 标识。"""
        if (
            self.workflow != self.basis.workflow
            or self.step != self.basis.step
            or self.schema_id != self.basis.schema_id
            or self.schema_version != self.basis.schema_version
        ):
            raise ValueError("Phản hồi ứng viên không nhất quán với hợp đồng basis")
        return self


def canonical_candidate_input(
    *,
    novel_id: str | None,
    workflow: str,
    step: str,
    schema_id: str,
    schema_version: int,
    source_refs: list[CandidateSourceRefV1 | Mapping[str, Any]],
    inputs: Mapping[str, Any],
) -> dict[str, Any]:
    """生成计算候选指纹所需的确定性白名单对象。

    Args:
        novel_id: 当前小说 ObjectId。
        workflow: 已登记工作流名称。
        step: 已登记步骤名称。
        schema_id: 候选严格 Schema 标识。
        schema_version: 候选 Schema 版本。
        source_refs: 正式事实来源及版本。
        inputs: 领域 Service 显式挑选的业务输入投影。

    Returns:
        键序列化稳定、来源引用排序稳定的纯 JSON 对象。
    """
    normalized_refs = [
        item.model_dump(mode="json")
        if isinstance(item, CandidateSourceRefV1)
        else CandidateSourceRefV1.model_validate(item).model_dump(mode="json")
        for item in source_refs
    ]
    normalized_refs.sort(key=lambda item: (item["resource_type"], item["id"], item["version"]))
    return {
        "novel_id": novel_id,
        "workflow": workflow,
        "step": step,
        "schema_id": schema_id,
        "schema_version": schema_version,
        "source_refs": normalized_refs,
        "inputs": dict(inputs),
    }


def compute_candidate_input_fingerprint(**kwargs: Any) -> str:
    """对候选正式输入和显式请求计算 canonical SHA-256。

    Args:
        kwargs: ``canonical_candidate_input`` 接受的全部命名参数。

    Returns:
        64 位小写十六进制 SHA-256 指纹。
    """
    canonical = canonical_candidate_input(**kwargs)
    encoded = json.dumps(
        canonical,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


def build_candidate_basis(**kwargs: Any) -> CandidateBasisV1:
    """在生成完成时构建带输入指纹的候选依据。

    Args:
        kwargs: ``canonical_candidate_input`` 接受的全部命名参数。

    Returns:
        可直接随领域候选返回浏览器的严格依据对象。
    """
    flow_ref = kwargs.pop("flow_ref")
    flow_snapshot = kwargs.pop("flow_snapshot")
    fingerprint = compute_candidate_input_fingerprint(**kwargs)
    return CandidateBasisV1(
        flow_ref=flow_ref,
        flow_snapshot=flow_snapshot,
        novel_id=kwargs["novel_id"],
        workflow=kwargs["workflow"],
        step=kwargs["step"],
        schema_id=kwargs["schema_id"],
        schema_version=kwargs["schema_version"],
        input_fingerprint=fingerprint,
        source_refs=kwargs["source_refs"],
    )


def require_current_candidate_basis(
    basis: CandidateBasisV1,
    *,
    current_source_versions: Mapping[tuple[str, str], int],
    current_fingerprint: str,
) -> None:
    """在确认写入前复核候选输入指纹与全部来源版本。

    Args:
        basis: 浏览器提交的候选依据。
        current_source_versions: Service 重读得到的资源类型、ID到版本映射。
        current_fingerprint: Service 按当前事实重新计算的输入指纹。

    Returns:
        依据仍有效时不返回内容。

    Raises:
        DomainApiError: 正式资源消失时 404；版本或指纹漂移时 409。
    """
    for source in basis.source_refs:
        identity = (source.resource_type, source.id)
        if identity not in current_source_versions:
            raise DomainApiError(
                "CANDIDATE_SOURCE_NOT_FOUND",
                "Tài nguyên chính thức trong căn cứ của ứng viên không còn tồn tại",
                status_code=404,
                details={"resource_type": source.resource_type, "id": source.id},
            )
        if current_source_versions[identity] != source.version:
            raise DomainApiError(
                "CANDIDATE_BASIS_CONFLICT",
                "Căn cứ của ứng viên đã hết hạn, hãy sinh lại dựa trên dữ kiện chính thức hiện tại",
                status_code=409,
            )
    if basis.input_fingerprint != current_fingerprint:
        raise DomainApiError(
            "CANDIDATE_FINGERPRINT_CONFLICT",
            "Đầu vào của ứng viên đã thay đổi, hãy sinh lại",
            status_code=409,
        )


__all__ = [
    "MAX_CANDIDATE_SOURCE_REFS",
    "CandidateBasisV1",
    "CandidateConfirmationEnvelopeV1",
    "CandidateGenerationEnvelopeV1",
    "CandidateIdempotencyKey",
    "CandidateSourceRefV1",
    "build_candidate_basis",
    "canonical_candidate_input",
    "compute_candidate_input_fingerprint",
    "require_current_candidate_basis",
]
