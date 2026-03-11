#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import requests
from bs4 import BeautifulSoup, Tag

ROOT = Path(__file__).resolve().parents[2]
SOURCES_DIR = ROOT / "data" / "sources"
PROCESSED_DIR = ROOT / "data" / "processed"
MANIFEST_PATH = SOURCES_DIR / "manifest.json"

USER_AGENT = "Mozilla/5.0 (compatible; BuildingTalkIngest/1.0; +https://example.local)"


@dataclass
class SourceDef:
    source_id: str
    title: str
    url: str
    kind: str
    license: str
    parser: Callable[[str], list[dict]]


def clean_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    return text


def soup_from_html(html: str) -> BeautifulSoup:
    soup = BeautifulSoup(html, "html.parser")
    for bad in soup.select("script, style, noscript, svg, nav, footer, header, form"):
        bad.decompose()
    return soup


def parse_generic_html(html: str) -> list[dict]:
    soup = soup_from_html(html)

    root: Tag | None = None
    for selector in [
        "main",
        "article",
        "#content",
        ".content",
        ".main",
        ".page-content",
        "#main-content",
        ".field--name-body",
    ]:
        node = soup.select_one(selector)
        if isinstance(node, Tag):
            root = node
            break

    if root is None:
        root = soup.body or soup

    sections: list[dict] = []
    current_heading = "Overview"
    bucket: list[str] = []
    skip_phrases = [
        "official websites use .gov",
        "secure .gov websites use https",
        "an official website of the united states government",
        "contact info",
        "last updated",
        "subscribe",
        "all rights reserved",
        "cookies",
        "accessibility",
        "privacy policy",
        "terms of use",
    ]

    def flush() -> None:
        nonlocal bucket, current_heading
        text = clean_text(" ".join(bucket))
        if text:
            sections.append({"heading": current_heading, "page": None, "text": text})
        bucket = []

    for node in root.find_all(["h1", "h2", "h3", "p", "li"]):
        if not isinstance(node, Tag):
            continue
        if node.name in {"h1", "h2", "h3"}:
            flush()
            heading = clean_text(node.get_text(" ", strip=True))
            current_heading = heading or "Section"
            continue

        text = clean_text(node.get_text(" ", strip=True))
        lowered = text.lower()
        if len(text) < 35:
            continue
        if any(phrase in lowered for phrase in skip_phrases):
            continue
        bucket.append(text)

    flush()

    if not sections:
        text = clean_text(root.get_text(" ", strip=True))
        if text:
            sections = [{"heading": "Overview", "page": None, "text": text}]

    skip_heading_phrases = [
        "contact info",
        "tags",
        "wedding ceremony fees",
        "reservation policy",
        "corporate events",
        "specs",
        "weddings",
    ]
    skip_text_phrases = [
        "skip to this park information section",
        "staff salary (per hour)",
        "refundable cleaning/damage deposit",
        "united states park police dispatch",
    ]

    deduped: list[dict] = []
    seen = set()
    for section in sections:
        heading = section["heading"]
        heading_l = heading.lower()
        content = section["text"]
        content_l = content.lower()
        if heading_l in skip_heading_phrases:
            continue
        if any(phrase in heading_l for phrase in ["contact info", "tags", "wedding", "corporate", "specs", "reservation"]):
            continue
        if any(phrase in content_l for phrase in skip_text_phrases):
            continue
        if content in seen:
            continue
        if heading_l == "exiting nps.gov":
            heading = "NPS Palace Overview"
        seen.add(content)
        deduped.append({"heading": heading, "page": section["page"], "text": content})

    return deduped


def parse_wikipedia_api(raw: str) -> list[dict]:
    payload = json.loads(raw)
    html = payload.get("parse", {}).get("text", "")
    return parse_generic_html(html)


def parse_wikidata_json(raw: str) -> list[dict]:
    payload = json.loads(raw)
    entity = payload.get("entities", {}).get("Q966263", {})

    labels = entity.get("labels", {})
    descriptions = entity.get("descriptions", {})
    claims = entity.get("claims", {})

    def claim_values(prop: str) -> list[str]:
        items = claims.get(prop, [])
        out: list[str] = []
        for item in items:
            try:
                value = item["mainsnak"]["datavalue"]["value"]
            except Exception:
                continue
            if isinstance(value, dict):
                if "id" in value:
                    out.append(value["id"])
                elif "time" in value:
                    out.append(value["time"])
                elif "latitude" in value and "longitude" in value:
                    out.append(f"{value['latitude']}, {value['longitude']}")
            else:
                out.append(str(value))
        return out

    sections = [
        {
            "heading": "Identity",
            "page": None,
            "text": clean_text(
                " ".join(
                    [
                        f"Label (en): {labels.get('en', {}).get('value', '')}.",
                        f"Description (en): {descriptions.get('en', {}).get('value', '')}.",
                    ]
                )
            ),
        },
        {
            "heading": "Key Claims",
            "page": None,
            "text": clean_text(
                " ".join(
                    [
                        f"Inception values: {', '.join(claim_values('P571')) or 'n/a'}.",
                        f"Coordinates: {', '.join(claim_values('P625')) or 'n/a'}.",
                        f"National Register reference number (P649): {', '.join(claim_values('P649')) or 'n/a'}.",
                        f"Website (P856): {', '.join(claim_values('P856')) or 'n/a'}.",
                        f"Heritage designation (P1435): {', '.join(claim_values('P1435')) or 'n/a'}.",
                    ]
                )
            ),
        },
    ]

    return [s for s in sections if s["text"]]


def parse_loc_item_json(raw: str) -> list[dict]:
    payload = json.loads(raw)

    sections = []
    title = payload.get("item", {}).get("title") or payload.get("title")
    if title:
        sections.append({"heading": "Title", "page": None, "text": clean_text(str(title))})

    for key, heading in [
        ("summary", "Summary"),
        ("notes", "Notes"),
        ("created_published", "Created/Published"),
        ("medium", "Medium"),
        ("subjects", "Subjects"),
        ("rights_advisory", "Rights"),
    ]:
        value = payload.get(key)
        if not value:
            continue
        if isinstance(value, list):
            text = " ".join(clean_text(str(v)) for v in value)
        else:
            text = clean_text(str(value))
        if text:
            sections.append({"heading": heading, "page": None, "text": text})

    if not sections:
        sections = [{"heading": "Raw JSON", "page": None, "text": clean_text(raw[:5000])}]

    return sections


def parse_loc_search_json(raw: str) -> list[dict]:
    payload = json.loads(raw)
    results = payload.get("results", [])[:25]

    sections: list[dict] = []
    for idx, result in enumerate(results, start=1):
        title = clean_text(str(result.get("title", "")))
        created = clean_text(str(result.get("created_published_date", "")))
        call_number = clean_text(str(result.get("call_number", "")))
        links = result.get("links", {}) or {}
        item_link = links.get("item", "")
        subjects = result.get("subjects", []) or []
        text = clean_text(
            f"Title: {title}. Created/published: {created}. Call number: {call_number}. "
            f"Item link: {item_link}. Subjects: {', '.join(subjects[:8])}."
        )
        if len(text) < 45:
            continue
        sections.append({"heading": f"Result {idx}", "page": None, "text": text})

    return sections


def fetch_text(url: str) -> str:
    response = requests.get(url, timeout=60, headers={"User-Agent": USER_AGENT})
    response.raise_for_status()
    return response.text


def write_processed(source: SourceDef, raw: str, sections: list[dict]) -> None:
    payload = {
        "building_id": "palace_of_fine_arts",
        "source_id": source.source_id,
        "title": source.title,
        "url": source.url,
        "license": source.license,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "sections": sections,
    }

    out_path = PROCESSED_DIR / f"{source.source_id}.json"
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def write_raw(source: SourceDef, raw: str) -> None:
    ext = "json" if source.kind == "json" else "html"
    out_path = SOURCES_DIR / f"{source.source_id}.{ext}"
    out_path.write_text(raw, encoding="utf-8")


def main() -> None:
    SOURCES_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    for existing in PROCESSED_DIR.glob("*.json"):
        existing.unlink(missing_ok=True)

    sources = [
        SourceDef(
            source_id="wikipedia_palace_of_fine_arts",
            title="Palace of Fine Arts - Wikipedia (API Parse)",
            url="https://en.wikipedia.org/w/api.php?action=parse&page=Palace_of_Fine_Arts&prop=text|sections&format=json&formatversion=2",
            kind="json",
            license="CC BY-SA 4.0",
            parser=parse_wikipedia_api,
        ),
        SourceDef(
            source_id="wikipedia_ppie_context",
            title="Panama-Pacific International Exposition - Wikipedia (API Parse)",
            url="https://en.wikipedia.org/w/api.php?action=parse&page=Panama%E2%80%93Pacific_International_Exposition&prop=text|sections&format=json&formatversion=2",
            kind="json",
            license="CC BY-SA 4.0",
            parser=parse_wikipedia_api,
        ),
        SourceDef(
            source_id="wikidata_palace_q966263",
            title="Wikidata - Palace of Fine Arts (Q966263)",
            url="https://www.wikidata.org/wiki/Special:EntityData/Q966263.json",
            kind="json",
            license="CC0",
            parser=parse_wikidata_json,
        ),
        SourceDef(
            source_id="palace_official_info_com",
            title="Palace of Fine Arts (Info)",
            url="https://palaceoffinearts.com/info/",
            kind="html",
            license="Site terms",
            parser=parse_generic_html,
        ),
        SourceDef(
            source_id="nps_palace_place",
            title="NPS - Palace of Fine Arts Place Page",
            url="https://www.nps.gov/places/000/palace-of-fine-arts.htm",
            kind="html",
            license="U.S. Government work",
            parser=parse_generic_html,
        ),
        SourceDef(
            source_id="nps_palace_prsf_visit",
            title="NPS - Presidio Visit Page: Palace of Fine Arts",
            url="https://www.nps.gov/prsf/planyourvisit/palace-of-fine-arts.htm",
            kind="html",
            license="U.S. Government work",
            parser=parse_generic_html,
        ),
        SourceDef(
            source_id="nps_ppie_palaces",
            title="NPS - PPiE Palaces",
            url="https://www.nps.gov/goga/learn/historyculture/ppie-palaces.htm",
            kind="html",
            license="U.S. Government work",
            parser=parse_generic_html,
        ),
        SourceDef(
            source_id="sf_public_works_restoration",
            title="San Francisco Public Works - Palace of Fine Arts Restoration",
            url="https://sfpublicworks.org/project/palace-fine-arts-restoration",
            kind="html",
            license="City and County of San Francisco site terms",
            parser=parse_generic_html,
        ),
        SourceDef(
            source_id="sf_recpark_palace_facility",
            title="SF Recreation and Parks - Palace of Fine Arts Facility",
            url="https://sfrecpark.org/Facilities/Facility/Details/Palace-of-Fine-Arts-423",
            kind="html",
            license="City and County of San Francisco site terms",
            parser=parse_generic_html,
        ),
        SourceDef(
            source_id="sf_recpark_palace_history_page",
            title="SF Recreation and Parks - Palace of Fine Arts",
            url="https://sfrecpark.org/917/Palace-of-Fine-Arts",
            kind="html",
            license="City and County of San Francisco site terms",
            parser=parse_generic_html,
        ),
        SourceDef(
            source_id="loc_palace_item_2013630485",
            title="Library of Congress Item 2013630485",
            url="https://www.loc.gov/pictures/item/2013630485/?fo=json",
            kind="json",
            license="See LOC rights statement",
            parser=parse_loc_item_json,
        ),
        SourceDef(
            source_id="loc_palace_search",
            title="Library of Congress Search - Palace of Fine Arts San Francisco",
            url="https://www.loc.gov/pictures/search/?q=Palace%20of%20Fine%20Arts%20San%20Francisco&fo=json",
            kind="json",
            license="See LOC rights statement",
            parser=parse_loc_search_json,
        ),
    ]

    manifest = []

    for source in sources:
        try:
            raw = fetch_text(source.url)
            sections = source.parser(raw)
            if not sections:
                print(f"skip {source.source_id}: no sections extracted")
                continue
            write_raw(source, raw)
            write_processed(source, raw, sections)
            manifest.append(
                {
                    "building_id": "palace_of_fine_arts",
                    "source_id": source.source_id,
                    "title": source.title,
                    "url": source.url,
                    "type": source.kind,
                    "license": source.license,
                }
            )
            print(f"processed {source.source_id}: {len(sections)} sections")
        except Exception as exc:
            print(f"failed {source.source_id}: {exc}")

    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote manifest: {MANIFEST_PATH}")


if __name__ == "__main__":
    main()
