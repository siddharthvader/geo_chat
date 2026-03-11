#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from uuid import uuid4

from openai import OpenAI
from psycopg import Connection

ROOT = Path(__file__).resolve().parents[2]
PROCESSED_DIR = ROOT / "data" / "processed"

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/buildingtalk")
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "openai")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL", "")
EMBED_MODEL = os.environ.get("EMBED_MODEL", "text-embedding-3-large")


def make_client() -> OpenAI:
    if LLM_PROVIDER == "openrouter":
        return OpenAI(
            api_key=OPENROUTER_API_KEY,
            base_url=OPENAI_BASE_URL or "https://openrouter.ai/api/v1",
        )
    return OpenAI(api_key=OPENAI_API_KEY, base_url=OPENAI_BASE_URL or None)


def vector_literal(values: list[float]) -> str:
    return "[" + ",".join(f"{v:.8f}" for v in values) + "]"


def chunk_text(text: str, chunk_size_words: int = 140, overlap_words: int = 25) -> list[str]:
    words = text.split()
    if not words:
        return []

    chunks = []
    idx = 0
    step = max(1, chunk_size_words - overlap_words)
    while idx < len(words):
        chunk = words[idx : idx + chunk_size_words]
        chunks.append(" ".join(chunk))
        idx += step
    return chunks


def upsert_document(
    conn: Connection,
    source_id: str,
    title: str,
    url: str,
    license_name: str,
    raw_text: str,
    building_id: str | None,
) -> str:
    existing = conn.execute("SELECT id::text FROM documents WHERE source_id = %s", (source_id,)).fetchone()
    if existing:
        try:
            conn.execute(
                "UPDATE documents SET title=%s, url=%s, license=%s, raw_text=%s, building_id=%s WHERE source_id=%s",
                (title, url, license_name, raw_text, building_id, source_id),
            )
        except Exception:
            conn.execute(
                "UPDATE documents SET title=%s, url=%s, license=%s, raw_text=%s WHERE source_id=%s",
                (title, url, license_name, raw_text, source_id),
            )
        return existing[0]

    doc_id = str(uuid4())
    try:
        conn.execute(
            "INSERT INTO documents (id, source_id, title, url, license, raw_text, building_id) VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (doc_id, source_id, title, url, license_name, raw_text, building_id),
        )
    except Exception:
        conn.execute(
            "INSERT INTO documents (id, source_id, title, url, license, raw_text) VALUES (%s, %s, %s, %s, %s, %s)",
            (doc_id, source_id, title, url, license_name, raw_text),
        )
    return doc_id


def clear_document_chunks(conn: Connection, document_id: str) -> None:
    conn.execute(
        "DELETE FROM embeddings WHERE chunk_id IN (SELECT id FROM chunks WHERE document_id = %s)",
        (document_id,),
    )
    conn.execute("DELETE FROM chunks WHERE document_id = %s", (document_id,))


def process_file(client: OpenAI, conn: Connection, path: Path) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    source_id = payload["source_id"]
    title = payload["title"]
    url = payload["url"]
    license_name = payload.get("license", "")
    building_id = payload.get("building_id")
    sections = payload.get("sections", [])

    raw_text = "\n".join(section.get("text", "") for section in sections)
    document_id = upsert_document(conn, source_id, title, url, license_name, raw_text, building_id)
    clear_document_chunks(conn, document_id)

    chunk_counter = 0
    for section in sections:
        text = section.get("text", "").strip()
        if not text:
            continue

        for chunk in chunk_text(text):
            chunk_id = str(uuid4())
            chunk_hash = hashlib.sha256(chunk.encode("utf-8")).hexdigest()
            metadata = {
                "heading": section.get("heading"),
                "page": section.get("page"),
            }

            conn.execute(
                "INSERT INTO chunks (id, document_id, chunk_index, content, content_hash, metadata) VALUES (%s, %s, %s, %s, %s, %s)",
                (chunk_id, document_id, chunk_counter, chunk, chunk_hash, json.dumps(metadata)),
            )

            embedding = client.embeddings.create(model=EMBED_MODEL, input=chunk).data[0].embedding
            conn.execute(
                "INSERT INTO embeddings (chunk_id, embedding, model) VALUES (%s, %s::vector, %s)",
                (chunk_id, vector_literal(embedding), EMBED_MODEL),
            )
            chunk_counter += 1

    print(f"indexed {source_id}: {chunk_counter} chunks")


def main() -> None:
    if not OPENAI_API_KEY and not OPENROUTER_API_KEY:
        raise SystemExit("Set OPENAI_API_KEY or OPENROUTER_API_KEY before indexing.")

    client = make_client()
    files = sorted(PROCESSED_DIR.glob("*.json"))
    if not files:
        raise SystemExit("No processed source files found. Run parse_sources.py first.")

    with Connection.connect(DATABASE_URL) as conn:
        for path in files:
            process_file(client, conn, path)
        conn.commit()


if __name__ == "__main__":
    main()
