"""Embedding 适配层（docs/04 §4）。

两个后端，接口一致，切换只看环境变量：
- `EMBEDDING_BACKEND=hashing`（默认）：字符 n-gram 哈希，零依赖、确定性、可离线 —— 开发与测试用；
- `EMBEDDING_BACKEND=bge-m3`：sentence-transformers 加载 `EMBEDDING_MODEL`（默认 BAAI/bge-m3，1024 维）。

两者维度同为 1024，便于平滑切换；跨后端混用会在检索时报维度不一致（store 层会明确提示）。
"""
from __future__ import annotations

import hashlib
import math
import os
import re
from typing import Protocol

DIM = 1024
_TOKEN_RE = re.compile(r"[A-Za-z0-9]+|[\u4e00-\u9fff]+")
DEFAULT_MODEL = "BAAI/bge-m3"


def tokens(text: str) -> list[str]:
    """中英混合分词：英文/数字按词；中文按字 + 双字组合。供 embedding 与关键词打分共用。"""
    result: list[str] = []
    for match in _TOKEN_RE.finditer(text or ""):
        token = match.group(0)
        if token[0].isascii():
            result.append(token.lower())
        else:
            result.extend(token)
            result.extend(token[i:i + 2] for i in range(len(token) - 1))
    return result


class Embedder(Protocol):
    name: str
    dim: int

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class HashingEmbedder:
    name = "hashing-char-ngram"
    dim = DIM

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(text) for text in texts]

    @staticmethod
    def _embed_one(text: str) -> list[float]:
        vector = [0.0] * DIM
        for token in tokens(text):
            digest = hashlib.md5(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % DIM
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign
        norm = math.sqrt(sum(value * value for value in vector))
        if norm > 0:
            vector = [value / norm for value in vector]
        return vector


class SentenceTransformerEmbedder:
    """bge-m3 / 任意 sentence-transformers 模型（按需安装，首次加载会下载权重）。"""

    def __init__(self, model_name: str = DEFAULT_MODEL):
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:  # pragma: no cover —— 依赖可选
            raise RuntimeError(
                "未安装 sentence-transformers，无法启用 bge-m3 后端："
                "请先执行 pip install sentence-transformers（首次运行需联网下载模型权重），"
                "或把 EMBEDDING_BACKEND 切回 hashing。"
            ) from exc
        self._model = SentenceTransformer(model_name)
        self.name = f"sentence-transformers:{model_name}"
        self.dim = int(self._model.get_sentence_embedding_dimension())

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors = self._model.encode(list(texts), normalize_embeddings=True,
                                     show_progress_bar=False)
        return [list(map(float, vector)) for vector in vectors]


_embedder: Embedder | None = None


def resolve_backend() -> str:
    return (os.getenv("EMBEDDING_BACKEND") or "hashing").strip().lower()


def build_embedder(backend: str | None = None) -> Embedder:
    backend = (backend or resolve_backend()).lower()
    if backend in ("hashing", "hash", "dev"):
        return HashingEmbedder()
    if backend in ("bge-m3", "bge_m3", "sentence-transformers", "st"):
        return SentenceTransformerEmbedder(os.getenv("EMBEDDING_MODEL") or DEFAULT_MODEL)
    raise ValueError(f"未知的 EMBEDDING_BACKEND：{backend!r}（可选：hashing / bge-m3）")


def get_embedder() -> Embedder:
    global _embedder
    if _embedder is None:
        _embedder = build_embedder()
    return _embedder


def reset_embedder() -> None:
    """测试或运行期切换后端后调用（重置缓存）。"""
    global _embedder
    _embedder = None


def cosine(a: list[float], b: list[float]) -> float:
    """余弦相似度（入参均为归一化向量，直接点积）。"""
    return sum(x * y for x, y in zip(a, b))
