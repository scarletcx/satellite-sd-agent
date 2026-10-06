"""知识库模块测试（docs/11 §1 L1/L5）。"""
import pytest

from app.tools import kb
from app.tools.kb.store import KbError, ingest_file
from tests.seed_kb import FIXTURES, seed


def test_seed_and_search():
    seed()
    result = kb.search("太阳翼面积与电池容量如何估算", top_k=5)
    assert result["results"], "应检索到电源样例"
    top = result["results"][0]
    assert top["doc_id"].startswith("power-")
    assert top["citation"]["is_synthetic"] is True
    assert top["score"] > 0
    assert top["citation"]["chunk_id"].startswith(top["doc_id"])


def test_search_no_evidence_returns_empty():
    seed()
    result = kb.search("足球比赛的越位规则与红黄牌", top_k=5)
    assert result["no_evidence"] is True
    assert result["results"] == []


def test_ingest_duplicate_rejected():
    seed()
    with pytest.raises(KbError):
        ingest_file(FIXTURES / "power.txt", module="power", doc_type="report",
                    license="synthetic", is_synthetic=True, title="电源分系统样例（合成）")


def test_delete_document(tmp_path):
    seed()
    before = kb.stats()["documents"]

    extra = tmp_path / "extra.txt"
    extra.write_text("临时测试语料：遥感小卫星总体设计流程说明。", encoding="utf-8")
    created = ingest_file(extra, module="other", doc_type="other", license="synthetic",
                          is_synthetic=True, title="临时样例")
    assert kb.stats()["documents"] == before + 1

    deleted = kb.delete_document(created["doc_id"])
    assert deleted["deleted_chunks"] >= 1
    assert kb.stats()["documents"] == before
