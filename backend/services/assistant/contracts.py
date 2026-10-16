"""小说助手的公开请求与工具参数，不接受任意数据库字段。"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.api.contracts import ObjectIdString


ResourceKind = Literal["novel", "volume", "arc", "scene", "chapter", "character", "faction", "location", "item", "world_rule", "character_relation", "faction_relation", "character_faction_binding", "character_volume_state", "faction_volume_state", "foreshadowing"]


class AssistantModel(BaseModel):
    """拒绝未声明参数，正文空白保持原样。"""

    model_config = ConfigDict(extra="forbid")


class ResourceRef(AssistantModel):
    """小说内一种资料的稳定位置。"""

    resource_type: ResourceKind
    id: str = Field(min_length=1, max_length=100)


class ContextAttachment(ResourceRef):
    """用户明确选定的资料或草稿，不把页面草稿当成已保存内容。"""

    fields: list[str] = Field(default_factory=list, max_length=30)
    usage: Literal["reference", "target"] = "reference"
    origin: Literal["saved", "draft"] = "saved"
    version: int | None = Field(default=None, ge=1)
    text: str | None = Field(default=None, max_length=12000)


class SessionCreate(AssistantModel):
    """新建当前小说的独立对话。"""

    title: str = Field(default="新对话", min_length=1, max_length=100)
    mode: Literal["review", "auto"] = "review"
    provider: str = Field(default="", max_length=100)
    model: str = Field(default="", max_length=200)


class SessionUpdate(AssistantModel):
    """修改会话设置；正在执行的轮次保留发送时的配置。"""

    title: str | None = Field(default=None, min_length=1, max_length=100)
    archived: bool | None = None
    mode: Literal["review", "auto"] | None = None
    provider: str | None = Field(default=None, max_length=100)
    model: str | None = Field(default=None, max_length=200)


class TurnRequest(AssistantModel):
    """发送时固定当前页面和作者附件。"""

    message: str = Field(min_length=1, max_length=16000)
    attachments: list[ContextAttachment] = Field(default_factory=list, max_length=20)
    location: ResourceRef | None = None
    writing_target: ResourceRef | None = None
    allow_navigation: bool = False
    execution_mode: Literal["auto", "review"] | None = None


class AnswerRequest(AssistantModel):
    """回答原问题，不能替换原目标、模型设置或修改修订。"""

    question_id: str = Field(min_length=1, max_length=100)
    message: str = Field(min_length=1, max_length=5000)
    confirmation_token: str | None = Field(default=None, max_length=64)


class ContinueRequest(AssistantModel):
    """零表示按剩余预算续跑；正数是作者明确追加的轮数。"""

    additional_rounds: int = Field(default=4, ge=0, le=16)


class WritingAnswerMeaning(AssistantModel):
    """外层用完整问答解释指代；子任务只接受这些固定创作动作。"""

    answer_id: str
    supported: bool
    actions: list[Literal["continue_request", "preserve_plot", "preserve_ending", "rewrite_expression", "expand_detail", "condense", "more_subtle", "more_direct", "more_dialogue", "less_dialogue", "preserve_viewpoint"]] = Field(max_length=4)
    resolved_by_answer_id: str | None = Field(default=None, description="这条简答的歧义已由哪条后来的明确作者回答消解；仅填真实回答ID，不填问题文字")


class WritingAnswerReview(AssistantModel):
    """按原顺序核实每个回答，不允许模型输出摘要、引文或剧情自由文本。"""

    answers: list[WritingAnswerMeaning]


class ChangeOperation(AssistantModel):
    """一项候选业务操作；服务端另行固定原版本和前值。"""

    action: Literal["create", "update", "delete", "restore", "reorder", "status", "preparation"]
    resource_type: ResourceKind
    id: str | None = Field(default=None, max_length=100)
    parent_id: str | None = Field(default=None, max_length=100)
    temporary_id: str | None = Field(default=None, pattern=r"^new_[A-Za-z0-9_]{1,60}$")
    fields: dict[str, Any] = Field(default_factory=dict)
    reason: str = Field(min_length=1, max_length=2000)

    @model_validator(mode="after")
    def reject_foreshadowing_write(self) -> "ChangeOperation":
        """首版助手只能读取伏笔，不暂存或执行其写入。

        Args:
            无。
        Returns:
            原业务允许的修改操作。
        """
        if self.resource_type == "foreshadowing":
            raise ValueError("伏笔只供读取，请由作者在伏笔工作台记录或修改")
        return self


class ChangeEdit(AssistantModel):
    """编辑未保存的业务候选，原依据不能由浏览器替换。"""

    expected_revision: int = Field(ge=1)
    operations: list[ChangeOperation] | None = Field(default=None, min_length=1, max_length=50)
    candidate: dict[str, Any] | None = None

    @model_validator(mode="after")
    def one_candidate(self):
        """普通修改与原任务候选只能提交一种。"""
        if (self.operations is None) == (self.candidate is None):
            raise ValueError("请提交普通修改或原任务候选中的一种")
        return self


class ChangeApproval(AssistantModel):
    """接受指定修改版本；危险操作和内容风险分别表达。"""

    expected_revision: int = Field(ge=1)
    confirm_lifecycle: bool = False
    accept_content_risk: bool = False
    confirmation_token: str | None = Field(default=None, max_length=64)


class ReviewIssue(AssistantModel):
    """内容检查必须指向真实来源，未检查内容独立列出。"""

    severity: Literal["conflict", "suggestion", "unchecked"]
    message: str = Field(min_length=1, max_length=2000)
    sources: list[ResourceRef] = Field(default_factory=list, max_length=20)


class ReviewResult(AssistantModel):
    """独立模型审核的结构化结论。"""

    summary: str = Field(min_length=1, max_length=2000)
    issues: list[ReviewIssue] = Field(default_factory=list, max_length=50)
    author_intent_supported: bool = False


class NavigationTarget(ResourceRef):
    """前端按业务类型映射内部位置，不执行模型返回的 URL。"""

    field: str | None = Field(default=None, max_length=100)


class FactChangeRequest(AssistantModel):
    """助手只提供拟改内容；依据、作者原话和 confirmed 均由服务端产生。"""

    resource_type: Literal["character", "character_relation", "item", "faction"]
    operation: Literal["create", "establish", "correct_initial", "change", "replace"]
    id: str | None = None
    candidate: dict[str, Any] | None = None
    position: dict[str, Any]
    after: dict[str, Any]
    replaces: dict[str, str] | str | None = None
    resolves: dict[str, list[str]] | list[str] | None = None
    evidence: dict[str, Any] | None = None
