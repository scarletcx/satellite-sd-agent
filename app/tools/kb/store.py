"""知识库存取与检索（docs/04 §3~§5）。

开发版：向量以 JSON 列表存于 SQLite，Python 内计算余弦（全量扫描，万级 chunk 可用）；
目标版：pgvector + HNSW（docs/08），对外接口不变。

检索时校验向量维度：语料由不同 embedding 后端写入时，维度不一致的 chunk 会被跳过并计数，
避免拿哈希向量去比语义向量。
"""
from __future__ import annotations

import hashlib
import re
import time
from datetime import datetime, timezone

from sqlalchemy import func, select

from app.db import new_session
from app.models import AppMeta, AuditLog, CorpusManifest, KbChunk
from app.tools.kb import vec_index
from app.tools.kb.chunking import chunk_text
from app.tools.kb.embedding import cosine, get_embedder, resolve_backend, tokens
from app.tools.kb.parsing import parse_file

MODULES = {"system", "power", "ttc", "data", "adcs", "orbit", "payload", "risk", "other"}
DOC_TYPES = {"standard", "manual", "report", "catalog", "lesson", "other"}

VEC_WEIGHT = 0.7
KW_WEIGHT = 0.3
# 初值 0.35（docs/04 §5）。标定记录（合成语料 4 篇）：正例 rank1 ≥ 0.52，无关查询 ≤ 0.17。
# 语料 / 切分 / embedding 变更后需重新标定并更新此处。
SCORE_THRESHOLD = 0.35


class KbError(ValueError):
    """知识库业务错误（映射为 400/409）。"""


def _slug(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return slug[:32] or "doc"


def _sha256(path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def _corpus_version(session) -> str:
    row = session.get(AppMeta, "corpus_version")
    return row.value if row else "corpus-v2026.10.0"


def _bump_corpus_version(session) -> str:
    current = _corpus_version(session)
    match = re.search(r"(\d+)$", current)
    number = int(match.group(1)) + 1 if match else 1
    version = re.sub(r"\d+$", f"{number}", current)
    session.merge(AppMeta(key="corpus_version", value=version))
    return version


def _match_filters(meta: dict, filters: dict) -> bool:
    if filters.get("module") and meta.get("module") != filters["module"]:
        return False
    if filters.get("doc_type") and meta.get("doc_type") != filters["doc_type"]:
        return False
    if filters.get("session_id") and meta.get("session_id") != filters["session_id"]:
        return False
    if filters.get("is_synthetic") is False and meta.get("is_synthetic"):
        return False
    if filters.get("year_from"):
        year = meta.get("year")
        if year and int(year) < int(filters["year_from"]):
            return False
    return True


def _keyword_score(query_tokens: set[str], chunk_tokens: set[str]) -> float:
    if not query_tokens:
        return 0.0
    return len(query_tokens & chunk_tokens) / len(query_tokens)


def ingest_file(
    path,
    *,
    module: str,
    doc_type: str,
    license: str,
    is_synthetic: bool = False,
    title: str | None = None,
    source_url: str | None = None,
    extra_meta: dict | None = None,
) -> dict:
    if module not in MODULES:
        raise KbError(f"module 非法：{module}")
    if doc_type not in DOC_TYPES:
        raise KbError(f"doc_type 非法：{doc_type}")
    if not license:
        raise KbError("license 必填")

    path = path if hasattr(path, "read_bytes") else path
    sha = _sha256(path)
    doc_id = f"{module}-{_slug(title or path.stem)}-{sha[:6]}"
    display_title = title or path.stem

    with new_session() as session:
        if session.get(CorpusManifest, doc_id) is not None:
            raise KbError(f"语料已存在：{doc_id}（先删除再重传）")

        pages = parse_file(path)
        embedder = get_embedder()
        count = 0
        vectors: list[tuple[str, list[float]]] = []
        for page_number, text in pages:
            for piece in chunk_text(text):
                count += 1
                vector = embedder.embed([piece])[0]
                chunk_id = f"{doc_id}-{count:03d}"
                vectors.append((chunk_id, vector))
                session.add(KbChunk(
                    id=chunk_id,
                    doc_id=doc_id,
                    content=piece,
                    embedding=vector,
                    page=page_number,
                    meta={
                        "module": module,
                        "doc_type": doc_type,
                        "is_synthetic": is_synthetic,
                        "license": license,
                        "source_url": source_url,
                        "page": page_number,
                        "embedding_model": embedder.name,
                        "embedding_dim": len(vector),
                        **(extra_meta or {}),
                    },
                ))
        if count == 0:
            raise KbError("解析后没有可入库的文本内容")

        session.add(CorpusManifest(
            doc_id=doc_id, title=display_title, source_url=source_url, license=license,
            sha256=sha, is_synthetic=is_synthetic, module=module, doc_type=doc_type, chunks=count,
        ))
        version = _bump_corpus_version(session)
        session.commit()

    # 向量索引（sqlite-vec）：写入失败不影响主流程（检索会回退到 JSON 全量扫描）
    vec_ok = vec_index.add_vectors(embedder.dim, vectors)

    return {"doc_id": doc_id, "title": display_title, "chunks": count, "corpus_version": version,
            "vector_index": "sqlite-vec" if vec_ok else "scan"}


def search(query: str, filters: dict | None = None, top_k: int = 8,
           candidate_k: int = 200, min_score: float | None = None) -> dict:
    filters = filters or {}
    threshold = SCORE_THRESHOLD if min_score is None else float(min_score)
    started = time.perf_counter()
    embedder = get_embedder()
    query_vector = embedder.embed([query])[0]
    query_tokens = set(tokens(query))
    dim_mismatch = 0
    index_mode = "scan"

    # sqlite-vec 先做近邻召回；不可用/索引为空时回退全量扫描
    vec_hits = vec_index.query_vectors(len(query_vector), query_vector, k=candidate_k)

    with new_session() as session:
        manifests = {m.doc_id: m for m in session.scalars(select(CorpusManifest)).all()}
        if vec_hits:
            index_mode = "sqlite-vec"
            ids = [chunk_id for chunk_id, _ in vec_hits]
            rows = session.scalars(select(KbChunk).where(KbChunk.id.in_(ids))).all()
        else:
            rows = session.scalars(select(KbChunk)).all()

        scored: list[tuple[float, KbChunk, dict]] = []
        for row in rows:
            meta = dict(row.meta or {})
            if not _match_filters(meta, filters):
                continue
            vector = list(row.embedding or [])
            if len(vector) != len(query_vector):
                dim_mismatch += 1
                continue
            similarity = cosine(query_vector, vector)
            keyword = _keyword_score(query_tokens, set(tokens(row.content)))
            score = VEC_WEIGHT * similarity + KW_WEIGHT * keyword
            if score >= threshold:
                scored.append((score, row, meta))

        scored.sort(key=lambda item: item[0], reverse=True)
        results = []
        for score, row, meta in scored[:top_k]:
            manifest = manifests.get(row.doc_id)
            results.append({
                "chunk_id": row.id,
                "doc_id": row.doc_id,
                "title": manifest.title if manifest else row.doc_id,
                "text": row.content,
                "score": round(score, 4),
                "citation": {
                    "doc_id": row.doc_id,
                    "chunk_id": row.id,
                    "title": manifest.title if manifest else row.doc_id,
                    "source_url": meta.get("source_url") or (manifest.source_url if manifest else None),
                    "page": meta.get("page"),
                    "module": meta.get("module"),
                    "is_synthetic": bool(meta.get("is_synthetic")),
                    "license": meta.get("license"),
                },
            })

    response = {"results": results, "took_ms": int((time.perf_counter() - started) * 1000),
                "no_evidence": not results, "dim_mismatch": dim_mismatch,
                "index_mode": index_mode,
                "indexed_chunks": vec_index.indexed_count(embedder.dim)}
    if dim_mismatch and not results:
        response["note"] = (f"{dim_mismatch} 个 chunk 的向量维度与当前 embedding 后端不一致"
                            "（可能来自另一个后端）；请用当前后端重新摄取，或切回原后端。")
    return response


def list_documents(module: str | None = None, doc_type: str | None = None,
                   page: int = 1, page_size: int = 20) -> dict:
    with new_session() as session:
        query = session.query(CorpusManifest)
        if module:
            query = query.filter(CorpusManifest.module == module)
        if doc_type:
            query = query.filter(CorpusManifest.doc_type == doc_type)
        total = query.count()
        rows = (query.order_by(CorpusManifest.fetched_at.desc())
                .offset((page - 1) * page_size).limit(page_size).all())
        items = [{
            "doc_id": m.doc_id, "title": m.title, "module": m.module, "doc_type": m.doc_type,
            "is_synthetic": m.is_synthetic, "license": m.license, "chunks": m.chunks,
            "fetched_at": m.fetched_at.isoformat() if m.fetched_at else None,
        } for m in rows]
    return {"items": items, "total": total, "page": page, "page_size": page_size}


def delete_document(doc_id: str, reviewer: str = "system") -> dict:
    with new_session() as session:
        manifest = session.get(CorpusManifest, doc_id)
        if manifest is None:
            raise KbError(f"语料不存在：{doc_id}")
        chunk_ids = [row[0] for row in session.query(KbChunk.id)
                     .filter(KbChunk.doc_id == doc_id).all()]
        deleted = (session.query(KbChunk)
                   .filter(KbChunk.doc_id == doc_id)
                   .delete(synchronize_session=False))
        session.delete(manifest)
        session.add(AuditLog(entity="corpus_manifest", entity_id=doc_id, field=None,
                             before={"chunks": manifest.chunks}, after=None,
                             who=reviewer, why="B4 delete"))
        version = _bump_corpus_version(session)
        session.commit()
    vec_index.delete_chunks(chunk_ids)
    return {"doc_id": doc_id, "deleted_chunks": deleted, "corpus_version": version}


def stats() -> dict:
    with new_session() as session:
        documents = session.scalar(select(func.count()).select_from(CorpusManifest)) or 0
        chunks = session.scalar(select(func.count()).select_from(KbChunk)) or 0
        last = session.scalar(select(func.max(CorpusManifest.fetched_at)))
        embedder = get_embedder()
        return {
            "documents": documents,
            "chunks": chunks,
            "corpus_version": _corpus_version(session),
            "embedding_model": embedder.name,
            "embedding_dim": embedder.dim,
            "embedding_backend": resolve_backend(),
            "vector_index": ("sqlite-vec" if vec_index.sqlite_vec_available() else "scan"),
            "vector_indexed_chunks": vec_index.indexed_count(embedder.dim),
            "last_ingest_at": last.isoformat() if last else None,
        }
