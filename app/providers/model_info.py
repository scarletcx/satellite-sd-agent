"""模型上下文窗口参考值（个人 agent 的自动压缩需要窗口大小）。

供应商的 /models 接口通常不返回上下文长度，这里按模型名做保守推断，
仅作为设置页的参考值；用户可在「对话与上下文」里手动调整实际窗口。
"""
from __future__ import annotations

import re

# 顺序敏感：先匹配更具体的模式
_HINTS: tuple[tuple[str, int], ...] = (
    (r"gpt-4\.1|gpt-5", 1_000_000),
    (r"gpt-4o|gpt-4-turbo", 128_000),
    (r"o[1-4](?:-|$)", 200_000),
    (r"claude", 200_000),
    (r"gemini.*(?:1\.5|2)", 1_000_000),
    (r"deepseek", 128_000),
    (r"qwen", 131_072),
    (r"glm", 128_000),
    (r"kimi|moonshot", 256_000),
    (r"llama", 128_000),
)


def context_window_for_model(model: str | None) -> int | None:
    name = (model or "").strip().lower()
    if not name:
        return None
    for pattern, window in _HINTS:
        if re.search(pattern, name):
            return window
    # 名称里显式写了 128k / 256K / 1m 的情况
    match = re.search(r"(\d{2,4})\s*k\b", name)
    if match:
        return int(match.group(1)) * 1024
    match = re.search(r"(\d(?:\.\d+)?)\s*m\b", name)
    if match:
        return int(float(match.group(1)) * 1_000_000)
    return None


def contexts_for_models(models: list[str]) -> dict[str, int | None]:
    return {model: context_window_for_model(model) for model in models}
