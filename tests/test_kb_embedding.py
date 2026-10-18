"""Embedding 后端切换与向量维度守卫测试（docs/04 §4）。"""
import pytest

from app.tools.kb import store
from app.tools.kb.embedding import (
    DIM,
    HashingEmbedder,
    build_embedder,
    get_embedder,
    reset_embedder,
)


class TinyEmbedder:
    """测试替身：固定维度、语义无关的向量。"""

    def __init__(self, dim: int):
        self.dim = dim
        self.name = f"tiny-{dim}"

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[1.0] + [0.0] * (self.dim - 1) for _ in texts]


def test_default_backend_is_hashing(monkeypatch):
    monkeypatch.delenv("EMBEDDING_BACKEND", raising=False)
    reset_embedder()
    embedder = get_embedder()
    assert isinstance(embedder, HashingEmbedder)
    assert embedder.dim == DIM
    reset_embedder()


def test_unknown_backend_rejected(monkeypatch):
    monkeypatch.setenv("EMBEDDING_BACKEND", "no-such-backend")
    with pytest.raises(ValueError, match="未知"):
        build_embedder()
    reset_embedder()


def test_bge_backend_without_dependency_shows_install_hint(monkeypatch):
    try:
        import sentence_transformers  # noqa: F401
    except ImportError:
        pass
    else:
        pytest.skip("环境已安装 sentence-transformers，跳过缺失提示测试")

    monkeypatch.setenv("EMBEDDING_BACKEND", "bge-m3")
    with pytest.raises(RuntimeError, match="sentence-transformers"):
        build_embedder()
    reset_embedder()


def test_dimension_mismatch_is_skipped_and_reported(monkeypatch, tmp_path):
    """用 8 维后端摄取、16 维后端检索 → chunk 被跳过并给出提示；切回后可命中。"""
    sample = tmp_path / "power-sample.txt"
    sample.write_text("太阳翼面积与电池容量估算：按轨道平均功耗反推。", encoding="utf-8")

    monkeypatch.setattr(store, "get_embedder", lambda: TinyEmbedder(8))
    ingested = store.ingest_file(sample, module="power", doc_type="report",
                                 license="synthetic", is_synthetic=True,
                                 title="维度守卫测试语料")
    doc_id = ingested["doc_id"]

    monkeypatch.setattr(store, "get_embedder", lambda: TinyEmbedder(16))
    mismatch = store.search("太阳翼 电池 容量")
    assert mismatch["results"] == []
    assert mismatch["dim_mismatch"] >= 1
    assert "不一致" in mismatch.get("note", "")

    monkeypatch.setattr(store, "get_embedder", lambda: TinyEmbedder(8))
    matched = store.search("太阳翼 电池 容量")
    assert any(item["doc_id"] == doc_id for item in matched["results"])

    store.delete_document(doc_id)
