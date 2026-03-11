from __future__ import annotations

import json
import re
from typing import Optional

from openai import OpenAI

from app.core.config import get_settings
from app.core.models import RetrievedChunk
from app.services.db import get_conn, vector_literal


def _make_client() -> OpenAI:
    settings = get_settings()
    if settings.llm_provider == "openrouter":
        return OpenAI(
            api_key=settings.openrouter_api_key,
            base_url=settings.openai_base_url or "https://openrouter.ai/api/v1",
        )
    return OpenAI(api_key=settings.openai_api_key, base_url=settings.openai_base_url or None)


def _tokenize(text: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9]+", text.lower()) if len(token) > 2}


def _keyword_retrieve(query: str, top_k: int, building_id: Optional[str] = None) -> list[RetrievedChunk]:
    settings = get_settings()
    processed_dir = settings.resolved_processed_dir
    terms = _tokenize(query)
    if not processed_dir.exists():
        return []

    scored: list[tuple[int, RetrievedChunk]] = []
    for path in sorted(processed_dir.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue

        title = payload.get("title", path.stem)
        url = payload.get("url", "")
        payload_building_id = payload.get("building_id")
        if building_id:
            if payload_building_id and payload_building_id != building_id:
                continue
            if not payload_building_id and building_id != "palace_of_fine_arts":
                continue
        sections = payload.get("sections", [])
        for idx, section in enumerate(sections):
            content = (section.get("text") or "").strip()
            if not content:
                continue
            chunk_terms = _tokenize(content)
            score = len(chunk_terms.intersection(terms))
            if score <= 0:
                continue

            scored.append(
                (
                    score,
                    RetrievedChunk(
                        chunk_id=f"{path.stem}:{idx}",
                        title=title,
                        url=url,
                        content=content,
                        metadata={
                            "heading": section.get("heading"),
                            "page": section.get("page"),
                            "source_id": payload.get("source_id"),
                            "retrieval": "keyword_fallback",
                        },
                    ),
                )
            )

    scored.sort(key=lambda row: row[0], reverse=True)
    return [chunk for _, chunk in scored[:top_k]]


def embed_text(text: str) -> list[float]:
    settings = get_settings()
    has_key = bool(settings.openrouter_api_key) if settings.llm_provider == "openrouter" else bool(settings.openai_api_key)
    if not has_key:
        raise RuntimeError("Missing API key for embedding generation.")

    client = _make_client()
    response = client.embeddings.create(model=settings.embed_model, input=text)
    return response.data[0].embedding


def retrieve(query: str, top_k: Optional[int] = None, building_id: Optional[str] = None) -> list[RetrievedChunk]:
    settings = get_settings()
    top_k = top_k or settings.top_k
    try:
        embedding = embed_text(query)

        with get_conn() as conn:
            if building_id:
                sql = """
                SELECT
                  chunks.id::text AS chunk_id,
                  documents.title,
                  documents.url,
                  chunks.content,
                  chunks.metadata
                FROM embeddings
                JOIN chunks ON chunks.id = embeddings.chunk_id
                JOIN documents ON documents.id = chunks.document_id
                WHERE documents.building_id = %s
                ORDER BY embeddings.embedding <-> %s::vector
                LIMIT %s
                """
                rows = conn.execute(sql, (building_id, vector_literal(embedding), top_k)).fetchall()
            else:
                sql = """
                SELECT
                  chunks.id::text AS chunk_id,
                  documents.title,
                  documents.url,
                  chunks.content,
                  chunks.metadata
                FROM embeddings
                JOIN chunks ON chunks.id = embeddings.chunk_id
                JOIN documents ON documents.id = chunks.document_id
                ORDER BY embeddings.embedding <-> %s::vector
                LIMIT %s
                """
                rows = conn.execute(sql, (vector_literal(embedding), top_k)).fetchall()

        return [RetrievedChunk(**row) for row in rows]
    except Exception:
        if settings.allow_keyword_fallback:
            return _keyword_retrieve(query, top_k, building_id)
        raise
