"""请求与响应的 Pydantic 模型。"""

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Pairing(BaseModel):
    """一条允许的（评审人，稿件）配对。"""

    model_config = ConfigDict(extra="forbid")

    reviewer_id: str = Field(..., description="评审人 ID")
    manuscript_id: str = Field(..., description="稿件 ID")

    @field_validator("reviewer_id", "manuscript_id")
    @classmethod
    def _non_empty(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("ID 不能为空字符串")
        return value


class AuditRequest(BaseModel):
    """POST /audit 的请求体。三组列表均非空，评审人与稿件数量相等。"""

    model_config = ConfigDict(extra="forbid")

    reviewers: list[str] = Field(..., min_length=1, description="评审人 ID 列表（非空）")
    manuscripts: list[str] = Field(..., min_length=1, description="稿件 ID 列表（非空）")
    allowed_pairings: list[Pairing] = Field(
        ..., min_length=1, description="允许配对列表（非空）"
    )

    @field_validator("reviewers", "manuscripts")
    @classmethod
    def _ids_non_empty(cls, values: list[str]) -> list[str]:
        for index, value in enumerate(values):
            if not isinstance(value, str) or not value or not value.strip():
                raise ValueError(
                    f"位置 {index} 的 ID 不能为空字符串"
                )
        return values


class OutputPair(BaseModel):
    """审计输出中的单条配对。"""

    reviewer_id: str
    manuscript_id: str


class AssignedPair(BaseModel):
    """确定性分配中的一条配对及其强制属性。

    - ``forced`` 为 true 时，该边出现在每一个完美匹配中（必然选择）。
    - ``forced`` 为 false 时，``alternative`` 给出一组**完整的**替代分配，
      该替代分配也是完美匹配，且不含本条配对。
    """

    reviewer_id: str
    manuscript_id: str
    forced: bool
    alternative: Optional[list[OutputPair]] = Field(
        default=None,
        description="forced=false 时为不含本边的一组完整替代分配",
    )


class AuditResponse(BaseModel):
    """存在完美匹配时的成功响应。"""

    perfect_match_exists: bool = True
    assignment: list[AssignedPair] = Field(
        description="按评审人 ID 排序后字典序最小的确定性分配，并逐对标注强制性"
    )


class HallWitness(BaseModel):
    """Hall 定理违例证书，证明不存在完美匹配。

    由最大匹配经交替路径构造：``reviewer_ids`` 为从所有未匹配评审人出发
    沿交替方向（非匹配边 评审人→稿件、匹配边 稿件→评审人）可达的评审人
    子集；``neighboring_manuscript_ids`` 恰为该子集在原 allowed_pairings
    中的全部邻居，故 ``|邻居| < |评审人|``，违反 Hall 条件。
    """

    reviewer_ids: list[str] = Field(
        description="Hall 违例评审人子集（按 ID 排序）"
    )
    neighboring_manuscript_ids: list[str] = Field(
        description="上述评审人在原 allowed_pairings 中的全部邻居稿件（按 ID 排序）"
    )
    deficiency: int = Field(
        ge=1,
        description="缺口：评审人数 - 邻居稿件数，等于全局未匹配人数",
    )


class ConflictResponse(BaseModel):
    """不存在完美匹配时的 409 响应（绝不返回部分成功）。"""

    perfect_match_exists: bool = False
    detail: str
    maximum_matching: list[OutputPair] = Field(
        description="基数最大的确定性匹配（完整展开，非配对结果）"
    )
    unmatched_reviewer_ids: list[str] = Field(description="未匹配的评审人 ID（已排序）")
    unmatched_manuscript_ids: list[str] = Field(description="未匹配的稿件 ID（已排序）")
    hall_witness: HallWitness = Field(
        description="Hall 定理违例证书：评审人子集的邻居数严格少于评审人数"
    )
