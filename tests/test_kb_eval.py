"""检索评测集回归（docs/04 §8）：Recall@3 ≥ 0.8。

评测集为合成语料上的起步版本；语料 / 切分 / 检索参数变更必须重跑本用例。
"""
import json
from pathlib import Path

from app.tools import kb
from tests.seed_kb import seed

EVAL_SET = Path(__file__).parent / "kb" / "eval-set.jsonl"
TOP_K = 3
RECALL_THRESHOLD = 0.8


def test_eval_set_recall():
    seed()
    cases = [json.loads(line) for line in EVAL_SET.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(cases) >= 8

    hits = 0
    for case in cases:
        result = kb.search(case["query"], filters=case.get("filters"), top_k=TOP_K)
        doc_ids = [item["doc_id"] for item in result["results"]]
        if any(doc_id.startswith(case["expected_doc_prefix"] + "-") for doc_id in doc_ids):
            hits += 1

    recall = hits / len(cases)
    assert recall >= RECALL_THRESHOLD, f"Recall@{TOP_K} = {recall:.2f}（低于 {RECALL_THRESHOLD}）"
