"""多供应商降级链 + 提示词渲染 + 结构化输出修复重试（ADR-0002 / docs/05 §4）。

行为约定：
- 供应商级失败（网络 / 限流 / 5xx）→ 换下一家；
- 输出级失败（非 JSON / 缺字段）→ 同家修复重试 ≤2 次，附校验错误后再试；
- 全部失败 → ProviderError（引擎置任务 failed，错误码 PROVIDER_FAILED）。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from pydantic import ValidationError

from app.providers.base import ProviderError
from app.providers.router import cost_cny
from app.providers.step_schemas import validate_step

STEP_PROMPTS = {
    "S1": "s1_parse/parse.v1.md",
    "S3": "s3_decompose/decompose.v1.md",
    "S4": "s4_params/params.v1.md",
    "S8": "s8_narrative/narrative.v1.md",
}
STEP_TEMPERATURES = {"S1": 0.2, "S3": 0.3, "S4": 0.1, "S8": 0.6}
REPAIR_RETRIES = 2

_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.S)


class OutputValidationError(ValueError):
    pass


class ProviderChain:
    def __init__(self, providers: list, *, prompt_dir: Path, repair_retries: int = REPAIR_RETRIES):
        if not providers:
            raise ProviderError("没有可用的 LLM 供应商：请配置 API Key，或设置 STUB_LLM=1 使用桩模式")
        self.providers = list(providers)
        self.prompt_dir = Path(prompt_dir)
        self.repair_retries = repair_retries

    # ------------------------------------------------------------ 对上层接口

    def chat_json(self, step: str, context: dict) -> tuple[dict, dict]:
        system = self._safety()
        user = self._render(self._load_prompt(step), context)
        last_error = ""

        for provider in self.providers:
            prompt = user
            for attempt in range(self.repair_retries + 1):
                try:
                    result = provider.call(system, prompt, STEP_TEMPERATURES.get(step, 0.2))
                except ProviderError as exc:
                    last_error = f"{provider.name}: {exc}"
                    break  # 供应商级失败 → 换下一家

                try:
                    payload = self._parse(step, result.text)
                except OutputValidationError as exc:
                    last_error = f"{provider.name}: 输出校验失败（{exc}）"
                    prompt = (user + "\n\n---\n上次输出无法通过校验：" + str(exc)[:300] +
                              "\n请重新输出，且只输出一个合法 JSON 对象（不要解释、不要 Markdown 代码块）。")
                    continue

                usage = {
                    "provider": provider.name,
                    "model": provider.model,
                    "tokens_in": result.tokens_in,
                    "tokens_out": result.tokens_out,
                    "cost_cny": cost_cny(provider.name, result.tokens_in, result.tokens_out),
                    "repair_attempts": attempt,
                }
                return payload, usage

        raise ProviderError(f"全部模型服务不可用或输出校验失败：{last_error}", provider="chain")

    # -------------------------------------------------------------- 内部实现

    def _safety(self) -> str:
        path = self.prompt_dir / "common" / "safety.v1.md"
        return path.read_text(encoding="utf-8").strip() if path.exists() else ""

    def _load_prompt(self, step: str) -> str:
        relative = STEP_PROMPTS.get(step)
        if relative is None:
            raise ProviderError(f"步骤 {step} 没有配置提示词文件", provider="chain")
        path = self.prompt_dir / relative
        if not path.exists():
            raise ProviderError(f"提示词文件不存在：{path}", provider="chain")
        return path.read_text(encoding="utf-8")

    @staticmethod
    def _render(template: str, context: dict) -> str:
        def dump(value) -> str:
            if isinstance(value, str):
                return value
            return json.dumps(value, ensure_ascii=False, indent=2)

        variables: dict[str, str] = {}
        for key, value in context.items():
            if key == "task_id":
                continue
            variables[key.upper()] = dump(value)
            variables[key.upper() + "_JSON"] = json.dumps(value, ensure_ascii=False, indent=2)
        for key in sorted(variables, key=len, reverse=True):  # 先替换长键，避免前缀误替换
            template = template.replace(f"<<{key}>>", variables[key])
        return template

    @staticmethod
    def _parse(step: str, text: str) -> dict:
        cleaned = _FENCE_RE.sub("", text or "").strip()
        try:
            payload = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            raise OutputValidationError(f"不是合法 JSON：{exc}") from exc
        if not isinstance(payload, dict):
            raise OutputValidationError("顶层必须是 JSON 对象")
        try:
            return validate_step(step, payload)
        except ValidationError as exc:
            first = exc.errors()[0] if exc.errors() else {}
            location = ".".join(str(part) for part in first.get("loc", ())) or "?"
            raise OutputValidationError(
                f"缺少 / 非法字段：{location}（{first.get('msg', '')}）") from exc
