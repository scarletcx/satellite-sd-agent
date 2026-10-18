"""各 LLM 步骤输出的最小校验模型（宽松：忽略未知字段，收紧关键字段）。"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class _Loose(BaseModel):
    model_config = ConfigDict(extra="ignore")


class S1Output(_Loose):
    goal: str = Field(min_length=1)
    constraints: dict = Field(default_factory=dict)
    clarifications: list = Field(default_factory=list)
    language: str = "zh"


class S2Output(_Loose):
    queries: list[str] = Field(min_length=1)


class S3Output(_Loose):
    configuration: dict = Field(default_factory=dict)
    subsystems: list = Field(default_factory=list)
    metrics: list = Field(default_factory=list)


class S4Output(_Loose):
    assumptions: list = Field(default_factory=list)
    mass: dict
    power: dict
    data: dict
    link: dict
    orbit: dict
    eps: dict


class S7Output(_Loose):
    suggestions: list = Field(default_factory=list)


class S8Output(_Loose):
    sections: dict


class ChatPlanOutput(_Loose):
    action: str = "answer"
    query: str | None = None
    answer: str | None = None
    goal: str | None = None
    args: dict = Field(default_factory=dict)


class ChatAnswerOutput(_Loose):
    answer: str = ""
    used_citations: list = Field(default_factory=list)


class ChatSummaryOutput(_Loose):
    summary: str = ""


class ChatCompactOutput(_Loose):
    summary: str = ""


class ChatMemoryOutput(_Loose):
    memories: list = Field(default_factory=list)


VALIDATORS: dict[str, type[BaseModel]] = {
    "S1": S1Output, "S2": S2Output, "S3": S3Output, "S4": S4Output,
    "S7": S7Output, "S8": S8Output,
    "CHAT_PLAN": ChatPlanOutput, "CHAT_ANSWER": ChatAnswerOutput, "CHAT_SUMMARY": ChatSummaryOutput,
    "CHAT_COMPACT": ChatCompactOutput, "CHAT_MEMORY": ChatMemoryOutput,
}


def validate_step(step: str, payload: dict) -> dict:
    model = VALIDATORS.get(step)
    if model is None:
        return payload
    return model.model_validate(payload).model_dump()
