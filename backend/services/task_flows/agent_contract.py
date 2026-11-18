"""资料整理节点、内嵌技能与固定报告格式。"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.api.contracts import ObjectIdString
from backend.llm.schemas.writing_pydantic import WritingSelectionV1


AGENT_TOOL_NAMES = ("get_scope", "list_directory", "search_book", "search_entities", "read_entity", "read_volume_state", "read_previous", "load_skill")
ENTITY_KINDS = ("character", "faction", "location", "item", "world_rule")
EntityKind = Literal["character", "faction", "location", "item", "world_rule"]


class AgentModel(BaseModel):
    "Từ chối các trường dọn dẹp không khai báo do mô hình hoặc trình duyệt gửi lên."

    model_config = ConfigDict(extra="forbid")


class AgentSkillV1(AgentModel):
    "Văn bản kỹ năng lưu kèm bản chỉnh sửa của luồng, không cho phép script hay đường dẫn bên ngoài."

    id: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z][A-Za-z0-9_-]*$")
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(min_length=1, max_length=1000)
    instructions: str = Field(min_length=1, max_length=12000)


DEFAULT_AGENT_SKILLS = [
    {"id": "story_boundaries", "name": "Giới hạn cốt truyện", "description": "Kiểm tra tuyến chính, vị trí hiện tại, phần trên và phần dưới cùng các cấp dưới đã lưu.",
     "instructions": "Hãy đọc phạm vi và mục lục hiện tại trước. Cốt truyện của quyển tiếp nối cốt truyện toàn sách, cốt truyện của vòng truyện tiếp nối cốt truyện của quyển này; giữ nguyên điểm đầu và điểm cuối đã chốt của các mục kề bên. Cấp dưới chỉ bổ sung phần cốt truyện chưa được bao phủ, không lặp lại nội dung đã lưu. Việc chưa có cấp dưới chính là nội dung lần này cần sinh, không phải thiếu tư liệu; tiêu đề và cách chia chờ ứng viên kiểm tra ở bước sau, không yêu cầu tác giả xác nhận lại ngân sách đã cho. Quyển cuối phải cho thấy sự khép lại, không hư cấu quyển kế tiếp."},
    {"id": "people_factions", "name": "Nhân vật và thế lực", "description": "Tìm nhân vật, thế lực có thể tái sử dụng cùng trạng thái quyển hiện tại.",
     "instructions": "Hãy tìm trước rồi đọc chi tiết, chọn nhân vật và thế lực thực sự cần theo vai trò trong cốt truyện. Mục tiêu quyển và điểm kết thúc của kế hoạch mới chỉ là thiết kế, tư liệu chưa xác định vị trí không được coi là dữ kiện hiện tại. Mỗi lựa chọn phải nêu rõ tác dụng; chỉ đề xuất thêm mới những vai trò mà tư liệu hiện có không đảm nhận được, không được dùng ID chưa đọc chi tiết."},
    {"id": "places_rules", "name": "Địa điểm và bối cảnh", "description": "Kiểm tra nơi chốn, vật phẩm và quy tắc thế giới.",
     "instructions": "Hãy tìm và đọc các địa điểm, vật phẩm, quy tắc hiện có để nâng đỡ hành động, kiểm tra khoảng cách, chức năng và giới hạn; chỉ đề xuất thêm mới khi không có địa điểm phù hợp. Văn phòng, sảnh ga, lối đi... nếu địa điểm hiện có đảm nhận được thì tái sử dụng trực tiếp, không vì chi tiết không gian tùy chọn mà chặn việc sinh nội dung. Chỉ báo vị trí cần bổ sung đối với khoảng trống thực thể thiết yếu đã xác minh mà tư liệu hiện có không đảm nhận được; không âm thầm lập hồ sơ trong phần văn bản chính."},
    {"id": "continuity", "name": "Mạch nối với phần trước", "description": "Đọc phần văn bản chính trước vị trí hiện tại và kiểm tra tính liên kết.",
     "instructions": "Hãy đọc phần trước đã viết, phân biệt phần văn bản chính thức và dàn ý; giữ nguyên sự kiện đã xảy ra, trạng thái nhân vật và quan hệ nhân quả. Không được bịa phần văn bản mà công cụ không trả về. Nêu rõ cốt truyện chưa được bao phủ cùng đề xuất tách nhỏ."},
]


class AgentNodeConfigV1(AgentModel):
    "Cấu hình có thể sửa của nút sắp xếp tài liệu."

    prompt: str = ""
    system_prompt: str = ""
    provider: str = ""
    provider_input: str = ""
    model: str = ""
    parameters: dict[str, Any] = Field(default_factory=dict)
    timeout_seconds: int | None = Field(default=None, gt=0)
    max_rounds: int = Field(default=8, ge=1, le=8)
    max_tool_calls: int = Field(default=24, ge=1, le=24)
    deduplicate_tool_budget: bool = False
    reference_unchanged_entities: bool = False
    index_structural_context: bool = False
    index_plot_children: bool = False
    chapter_context_version: Literal[1] | None = Field(default=None, exclude_if=lambda value: value is None)
    tools: list[Literal["get_scope", "list_directory", "search_book", "search_entities", "read_entity", "read_volume_state", "read_previous", "load_skill"]] = Field(default_factory=lambda: list(AGENT_TOOL_NAMES), min_length=1, max_length=8)
    skills: list[AgentSkillV1] = Field(default_factory=lambda: [AgentSkillV1.model_validate(value) for value in DEFAULT_AGENT_SKILLS], max_length=20)
    schema_defs: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def unique_tools_and_skills(self) -> "AgentNodeConfigV1":
        """工具与技能使用唯一 ID，避免不同内容共用一个入口。"""
        if len(self.tools) != len(set(self.tools)) or len(self.skills) != len({skill.id for skill in self.skills}):
            raise ValueError("Tên công cụ và ID kỹ năng không được trùng nhau")
        if "get_scope" not in self.tools:
            raise ValueError("Việc sắp xếp tư liệu bắt buộc bật get_scope")
        return self


class PreparedTargetV1(AgentModel):
    "Tiểu thuyết và vị trí thao tác do máy chủ cố định."

    novel_id: ObjectIdString
    target_type: Literal["volume", "arc", "scene", "chapter"]
    target_id: ObjectIdString
    reading_version: Literal[1] | None = None
    reading_intent: Literal["chapter_before", "chapter_after", "append", "replan"] | None = None


class EntitySelectionReasonV1(AgentModel):
    "Lý do cụ thể để dùng thực thể đã đọc."

    resource_type: EntityKind
    id: str = Field(min_length=1, max_length=100)
    reason: str = Field(min_length=1, max_length=2000)


class EntityNeedV1(AgentModel):
    "Một trách nhiệm cốt truyện mà tài liệu hiện tại không đảm đương được."

    resource_type: EntityKind
    role: str = Field(min_length=1, max_length=1000)
    reason: str = Field(min_length=1, max_length=2000)


class EntityNewCountsV1(AgentModel):
    "Số lượng đề xuất cho từng loại thực thể mới, cuối cùng vẫn hợp lệ hóa theo giới hạn của miền tương ứng."

    character: int = Field(default=0, ge=0, le=30)
    faction: int = Field(default=0, ge=0, le=30)
    location: int = Field(default=0, ge=0, le=30)
    item: int = Field(default=0, ge=0, le=30)
    world_rule: int = Field(default=0, ge=0, le=30)


class PreparationMissingV1(AgentModel):
    "Các mục thiếu đã xác minh mà tài liệu hiện có không đáp ứng được và sẽ chặn lần sinh này."

    field: str = Field(min_length=1, max_length=200, description="Vị trí của tư liệu hiện có hoặc thực thể cần thiết thực sự bị thiếu, không phải cấp dưới, tiêu đề lần này cần sinh hay ngân sách đã cho.")
    message: str = Field(min_length=1, max_length=2000, description="Hãy nêu đã tìm thấy gì, vì sao tư liệu hiện có không đủ nâng đỡ việc sinh lần này và tác giả cần bổ sung gì; chi tiết địa điểm tái sử dụng được hay đề xuất tùy chọn không thuộc mục thiếu.")


class ChapterParentExcerptV1(AgentModel):
    "Áp dụng một đoạn nguyên văn liên tiếp trong các trường tổ tiên đã thực sự đọc; không nhận chṗ nối."

    resource_type: Literal["novel", "volume", "arc", "scene"]
    id: ObjectIdString
    version: int = Field(ge=1)
    field: Literal["plot", "worldview", "core_seed", "core_idea", "summary", "planning.continuity_notes",
                   "planning.premise", "planning.major_conflict", "planning.goal", "planning.start_state", "planning.end_state"]
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    quote: str = Field(min_length=1)


class ChapterSourcesV1(AgentModel):
    "Nguyên văn tổ tiên, phần trước đã đọc và quan hệ nhân vật mà chương này áp dụng; danh sách rỗng nghĩa là không áp dụng."

    parent_excerpts: list[ChapterParentExcerptV1] = Field(max_length=30)
    previous_chapter_ids: list[ObjectIdString] = Field(max_length=100)
    relation_ids: list[str] = Field(max_length=100)


class PreparedContextV1(AgentModel):
    "Báo cáo tư liệu cố định cần cho bước tạo sinh tiếp theo; chi tiết chính thức do server điền vào."

    schema_version: Literal[1] = 1
    chapter_sources: ChapterSourcesV1 | None = Field(default=None, exclude_if=lambda value: value is None)
    target: PreparedTargetV1
    boundaries: str = Field(min_length=1, max_length=12000)
    selected_entities: WritingSelectionV1 = Field(default_factory=WritingSelectionV1)
    selection_reasons: list[EntitySelectionReasonV1] = Field(default_factory=list, max_length=250)
    entity_needs: list[EntityNeedV1] = Field(default_factory=list, max_length=150)
    new_counts: EntityNewCountsV1 = Field(default_factory=EntityNewCountsV1)
    suggested_count: int = Field(ge=0, le=20, description="Số cấp dưới cần thêm mới trong lần này. Còn cốt truyện chưa lên kế hoạch thì phải từ 1 đến 20; toàn bộ cốt truyện đã được cấp dưới hiện có bao phủ thì bắt buộc bằng 0. Tuân theo số lượng cố định nêu rõ trong đầu vào lần này, nếu là auto thì tự ước lượng.")
    coverage: str = Field(min_length=1, max_length=12000, description="Lần lượt nêu cấp dưới hiện có đã bao phủ gì, còn lại gì; khi hiện tại chưa có cấp dưới thì không được nói cốt truyện đã được bao phủ.")
    remaining: bool = Field(strict=True, description="Còn nội dung chưa được bao phủ cần sinh trong lần này hay không. true nghĩa là vẫn cần sinh, suggested_count phải lớn hơn 0; false nghĩa là nội dung hiện có bao phủ đầy đủ, không cần thêm mới, suggested_count phải bằng 0. Không phải là \"tư liệu còn cần bổ sung hay không\".")
    missing_required: list[PreparationMissingV1] = Field(default_factory=list, max_length=100, description="Chỉ điền những mục thiếu đã xác minh mà không bổ sung thì không thể sinh; khi tư liệu đã đủ thì điền []. Không được đưa vào nội dung lần này chờ sinh, tham số tác giả đã chốt, văn phòng hay lối đi dùng theo địa điểm hiện có, và đề xuất chi tiết hóa tùy chọn.")
    entity_details: list[dict[str, Any]] = Field(default_factory=list, max_length=250)
    volume_states: list[dict[str, Any]] = Field(default_factory=list, max_length=500)
    relations: list[dict[str, Any]] = Field(default_factory=list, max_length=500)
    previous_text: list[dict[str, Any]] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def remaining_count(self) -> "PreparedContextV1":
        """生成数量必须与是否还有待生成内容一致。"""
        if self.remaining and self.suggested_count == 0:
            raise ValueError("Khi còn cốt truyện chưa lên kế hoạch, số lượng đề xuất không được bằng 0")
        if not self.remaining and self.suggested_count != 0:
            raise ValueError("Khi nói cốt truyện đã được bao phủ toàn bộ, số lượng đề xuất bắt buộc bằng 0; nếu vẫn cần thêm nội dung, hãy chuyển remaining thành true")
        return self


class BookReadV1(AgentModel):
    "Lần đọc công cụ cố định có thể phát lại, gồm cả kết quả rỗng và phân trang."

    tool: Literal["get_scope", "list_directory", "search_book", "search_entities", "read_entity", "read_volume_state", "read_previous"]
    arguments: dict[str, Any]
    scope: PreparedTargetV1
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
