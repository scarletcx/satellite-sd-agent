"""sqlite-vec 索引测试（可用时启用；同时验证不可用时回退）。"""
import pytest

from app.tools.kb import vec_index


def test_sqlite_vec_available_in_this_env():
    assert vec_index.sqlite_vec_available(), "测试环境应安装 sqlite-vec"


def test_add_query_delete_roundtrip():
    dim = 8
    vectors = [
        ("chunk-a", [1.0, 0, 0, 0, 0, 0, 0, 0]),
        ("chunk-b", [0, 1.0, 0, 0, 0, 0, 0, 0]),
        ("chunk-c", [0.7, 0.7, 0, 0, 0, 0, 0, 0]),
    ]
    assert vec_index.add_vectors(dim, vectors) is True

    hits = vec_index.query_vectors(dim, [1.0, 0, 0, 0, 0, 0, 0, 0], k=3)
    assert hits, "应能查询到近邻"
    assert hits[0][0] == "chunk-a"
    assert vec_index.indexed_count(dim) >= 3

    assert vec_index.delete_chunks(["chunk-a"]) is True
    remaining = [chunk_id for chunk_id, _ in vec_index.query_vectors(
        dim, [1.0, 0, 0, 0, 0, 0, 0, 0], k=5)]
    assert "chunk-a" not in remaining


def test_fallback_when_extension_unavailable(monkeypatch):
    monkeypatch.setattr(vec_index, "sqlite_vec_available", lambda: False)
    assert vec_index.query_vectors(8, [1.0, 0, 0, 0, 0, 0, 0, 0]) is None
    assert vec_index.add_vectors(8, [("x", [1.0, 0, 0, 0, 0, 0, 0, 0])]) is False
    assert vec_index.indexed_count(8) is None
