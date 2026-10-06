"""LLM 供应商接口与通用类型（ADR-0002）。

分层：
- RawProvider（本文件）：底层供应商调用，`call(system, user, temperature) -> ProviderCallResult`；
- ProviderChain（chain.py）：降级链 + 提示词渲染 + 结构化输出修复重试；
- 对步骤层统一暴露：`provider.chat_json(step, context) -> (payload, usage)`。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class ProviderError(RuntimeError):
    """供应商调用失败（网络 / 限流 / 5xx / 鉴权 / 全部不可用）。"""

    def __init__(self, message: str, *, provider: str = "", status: int | None = None):
        super().__init__(message)
        self.provider = provider
        self.status = status


@dataclass
class ProviderCallResult:
    text: str
    tokens_in: int = 0
    tokens_out: int = 0


class RawProvider(Protocol):
    name: str
    model: str

    def call(self, system: str, user: str, temperature: float) -> ProviderCallResult: ...
