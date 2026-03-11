#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

import pdfplumber
import trafilatura

ROOT = Path(__file__).resolve().parents[2]
SOURCES_DIR = ROOT / "data" / "sources"
PROCESSED_DIR = ROOT / "data" / "processed"
MANIFEST_PATH = SOURCES_DIR / "manifest.json"


def parse_html(path: Path) -> list[dict]:
    raw = path.read_text(encoding="utf-8", errors="ignore")
    extracted = trafilatura.extract(raw, include_comments=False, include_tables=False)
    text = extracted or ""
    if not text.strip():
        text = raw

    paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
    sections = []
    for i, para in enumerate(paragraphs):
        sections.append({"heading": f"Paragraph {i+1}", "page": None, "text": para})
    return sections


def parse_pdf(path: Path) -> list[dict]:
    sections = []
    with pdfplumber.open(path) as pdf:
        for page_index, page in enumerate(pdf.pages, start=1):
            text = (page.extract_text() or "").strip()
            if not text:
                continue
            sections.append(
                {
                    "heading": f"Page {page_index}",
                    "page": page_index,
                    "text": text,
                }
            )
    return sections


def process_source(source: dict) -> None:
    source_id = source["source_id"]
    source_type = source["type"]
    in_path = SOURCES_DIR / f"{source_id}.{ 'pdf' if source_type == 'pdf' else 'html' }"

    if not in_path.exists():
        print(f"skip {source_id}: missing {in_path.name}")
        return

    if source_type == "pdf":
        sections = parse_pdf(in_path)
    else:
        sections = parse_html(in_path)

    payload = {
        "source_id": source_id,
        "title": source["title"],
        "url": source["url"],
        "license": source.get("license", ""),
        "sections": sections,
    }

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    out_path = PROCESSED_DIR / f"{source_id}.json"
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"processed {source_id} -> {out_path}")


def main() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    for source in manifest:
        process_source(source)


if __name__ == "__main__":
    main()
