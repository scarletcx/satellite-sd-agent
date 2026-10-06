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


class S8Output(_Loose):
    sections: dict


VALIDATORS: dict[str, type[BaseModel]] = {
    "S1": S1Output, "S3": S3Output, "S4": S4Output, "S8": S8Output,
}


def validate_step(step: str, payload: dict) -> dict:
    model = VALIDATORS.get(step)
    if model is None:
        return payload
    return model.model_validate(payload).model_dump()
