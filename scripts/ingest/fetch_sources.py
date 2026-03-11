#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = ROOT / "data" / "sources" / "manifest.json"
SOURCES_DIR = ROOT / "data" / "sources"


EXT_BY_TYPE = {
    "html": ".html",
    "pdf": ".pdf",
    "txt": ".txt",
}


def fetch_one(source: dict) -> None:
    source_id = source["source_id"]
    source_type = source["type"]
    url = source["url"]

    ext = EXT_BY_TYPE.get(source_type, ".bin")
    out_path = SOURCES_DIR / f"{source_id}{ext}"

    response = requests.get(url, timeout=30)
    response.raise_for_status()
    out_path.write_bytes(response.content)
    print(f"saved {source_id} -> {out_path}")


def main() -> None:
    SOURCES_DIR.mkdir(parents=True, exist_ok=True)
    sources = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    for source in sources:
        try:
            fetch_one(source)
        except Exception as exc:
            print(f"failed {source['source_id']}: {exc}")


if __name__ == "__main__":
    main()
