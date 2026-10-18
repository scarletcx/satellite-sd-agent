"""S2 检索先例与约束（工具步）：模型生成检索式 → 多路 kb.search → 合并去重 → Citations。

检索式由模型基于任务书生成（失败时回退到固定的分系统检索式）；检索不过滤语料类型
（真实语料与合成语料都参与召回）。结果落盘 citations.json，供断点恢复与 Word 附录引用表使用。
"""
from __future__ import annotations

import json

from app.providers import chat_json
from app.providers.base import ProviderError
from app.tools import kb
from app.tracing import task_dir

# 模型不可用时的固定检索式（按分系统，docs/05 §S2：3~5 个检索式）
_FALLBACK_QUERIES = (
    "太阳翼 电源 电池 余量",
    "数据量 压缩 存储 下行 数传",
    "测控 地面站 过境 链路 余量",
    "轨道 覆盖 重访 太阳同步",
)
_TOP_PER_QUERY = 2
_TOP_TOTAL = 5
_MAX_QUERIES = 5
_MIN_QUERIES = 3


def _model_queries(ctx: dict) -> list[str]:
    """让模型根据任务书生成检索式；失败或不足时用固定检索式补齐。"""
    try:
        payload = chat_json("S2", {
            "task_id": ctx["task_id"],
            "mission_request": ctx["mission_request"],
        })
        queries = [str(item).strip() for item in payload.get("queries", []) if str(item).strip()]
    except ProviderError:
        queries = []

    if len(queries) < _MIN_QUERIES:
        queries = [*queries, *_FALLBACK_QUERIES]

    seen: set[str] = set()
    ordered: list[str] = []
    for query in queries:
        key = query.lower()
        if key not in seen:
            seen.add(key)
            ordered.append(query)
    return ordered[:_MAX_QUERIES]


def run(ctx: dict) -> dict:
    request = ctx["mission_request"]
    queries = [request.get("goal", ""), *_model_queries(ctx)]

    merged: dict[str, dict] = {}
    for query in queries:
        if not str(query).strip():
            continue
        result = kb.search(str(query), top_k=_TOP_PER_QUERY)
        for item in result["results"]:
            current = merged.get(item["chunk_id"])
            if current is None or item["score"] > current["score"]:
                merged[item["chunk_id"]] = item

    ordered = sorted(merged.values(), key=lambda item: item["score"], reverse=True)[:_TOP_TOTAL]

    citations: list[dict] = []
    for index, item in enumerate(ordered, start=1):
        citation = dict(item["citation"])
        citation["id"] = f"S{index}"
        citation["url"] = citation.pop("source_url", None) or ""
        citation["type"] = "合成" if citation.get("is_synthetic") else "真实"
        citations.append(citation)

    ctx["citations"] = citations
    (task_dir(ctx["task_id"]) / "citations.json").write_text(
        json.dumps(citations, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return {"type": "tool", "output_ref": "citations.json",
            "citations": len(citations), "queries": queries, "no_evidence": not citations}
