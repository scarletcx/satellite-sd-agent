"""文本切片（docs/04 §3）：段落/句子优先，目标 600 字符，块间重叠 15%。"""
from __future__ import annotations

import re

TARGET_CHARS = 600
OVERLAP_RATIO = 0.15

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[。！？!?；;])|(?<=\n)")


def chunk_text(text: str, target: int = TARGET_CHARS, overlap_ratio: float = OVERLAP_RATIO) -> list[str]:
    text = re.sub(r"[ \t]+", " ", text or "")
    sentences = [piece.strip() for piece in _SENTENCE_SPLIT_RE.split(text) if piece and piece.strip()]

    chunks: list[str] = []
    current = ""
    for sentence in sentences:
        if len(current) + len(sentence) <= target:
            current += sentence
            continue
        if current.strip():
            chunks.append(current.strip())
        while len(sentence) > target:  # 超长句硬切
            chunks.append(sentence[:target].strip())
            sentence = sentence[int(target * (1 - overlap_ratio)):]
        current = sentence
    if current.strip():
        chunks.append(current.strip())

    if overlap_ratio > 0 and len(chunks) > 1:
        overlap_chars = int(target * overlap_ratio)
        merged = [chunks[0]]
        for previous, following in zip(chunks, chunks[1:]):
            merged.append((previous[-overlap_chars:] + following).strip())
        chunks = merged

    return [chunk for chunk in chunks if chunk]
