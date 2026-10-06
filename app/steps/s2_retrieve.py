"""S2 检索先例与约束（工具步）：按分系统多路 kb.search → 合并去重 → Citations。

检索结果落盘 citations.json，供断点恢复（S7 之后继续执行时）与 Word 附录引用表使用。
"""
from __future__ import annotations

import json

from app.tools import kb
from app.tracing import task_dir

# 按分系统的检索式（docs/05 §S2：3~5 个检索式）
_SUBSYSTEM_QUERIES = (
    "太阳翼 电源 电池 余量",
    "数据量 压缩 存储 下行 数传",
    "测控 地面站 过境 链路 余量",
    "轨道 覆盖 重访 太阳同步",
)
_TOP_PER_QUERY = 2
_TOP_TOTAL = 5


def run(ctx: dict) -> dict:
    request = ctx["mission_request"]
    queries = (request.get("goal", ""), *_SUBSYSTEM_QUERIES)

    merged: dict[str, dict] = {}
    for query in queries:
        if not str(query).strip():
            continue
        result = kb.search(str(query), filters={"is_synthetic": True}, top_k=_TOP_PER_QUERY)
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
            "citations": len(citations), "no_evidence": not citations}
