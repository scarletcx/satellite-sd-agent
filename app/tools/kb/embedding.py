"""Embedding 适配层（docs/04 §4）。

开发版：HashingEmbedder（字符 n-gram 哈希，确定性、零依赖、可离线）——保证链路可跑、测试可复现。
目标版：bge-m3（1024 维，sentence-transformers）；接口不变，替换 get_embedder 即可（ADR-0002）。
"""
from __future__ import annotations

import hashlib
import math
import re
from typing import Protocol

DIM = 1024
_TOKEN_RE = re.compile(r"[A-Za-z0-9]+|[\u4e00-\u9fff]+")


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


_embedder = HashingEmbedder()


def get_embedder() -> HashingEmbedder:
    return _embedder  # TODO(bge-m3)：接入 sentence-transformers 后替换


def cosine(a: list[float], b: list[float]) -> float:
    """余弦相似度（入参均为归一化向量，直接点积）。"""
    return sum(x * y for x, y in zip(a, b))
