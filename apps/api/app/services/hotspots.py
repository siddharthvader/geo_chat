from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Optional

from app.core.config import get_settings
from app.core.models import Hotspot
from app.services.buildings import get_hotspots_file_for_building, resolve_building_id


@lru_cache
def load_hotspots(building_id: Optional[str] = None) -> list[Hotspot]:
    resolved_building_id = resolve_building_id(building_id)
    hotspots_file = get_hotspots_file_for_building(resolved_building_id)
    path = (Path(__file__).resolve().parents[4] / hotspots_file).resolve()
    if not path.exists():
        path = get_settings().resolved_hotspots_path
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    return [Hotspot(**item) for item in data]


def summarize_hotspots_for_prompt(building_id: Optional[str] = None) -> list[dict[str, object]]:
    return [
        {
            "id": h.id,
            "name": h.name,
            "tags": h.tags,
            "description": h.description,
        }
        for h in load_hotspots(building_id)
    ]


def _normalize_token(token: str) -> str:
    token = re.sub(r"[^a-z0-9]+", "", token.lower())
    if len(token) > 4 and token.endswith("s"):
        token = token[:-1]
    return token


def _tokenize(text: str) -> set[str]:
    stopwords = {
        "what",
        "where",
        "when",
        "why",
        "how",
        "tell",
        "about",
        "building",
        "palace",
        "fine",
        "art",
        "arts",
        "information",
        "detail",
        "details",
        "history",
        "overview",
        "general",
    }
    tokens = set()
    for part in re.split(r"\W+", text):
        token = _normalize_token(part)
        if not token or token in stopwords:
            continue
        tokens.add(token)
    return tokens


QUERY_EXPANSIONS: dict[str, set[str]] = {
    "dome": {"rotunda", "coffer", "ceiling"},
    "coffer": {"dome", "ceiling"},
    "lady": {"weeping", "sculpture", "statue"},
    "weeping": {"lady", "sculpture"},
    "column": {"colonnade", "capital", "corinthian", "peristyle"},
    "colonnade": {"column", "arcade"},
    "lagoon": {"water", "reflection", "axis"},
    "ruin": {"aesthetic", "romantic"},
    "frieze": {"entablature"},
    "reconstruction": {"plaque", "1964", "1974"},
}


def _expanded_terms(terms: set[str]) -> set[str]:
    expanded = set(terms)
    for term in list(terms):
        expanded.update(QUERY_EXPANSIONS.get(term, set()))
    return expanded


def rank_hotspots_by_query(query: str, building_id: Optional[str] = None) -> list[dict[str, object]]:
    normalized_query = " ".join(_tokenize(query))
    base_terms = _tokenize(query)
    terms = _expanded_terms(base_terms)
    scored: list[tuple[float, int, Hotspot, list[str]]] = []

    for hotspot in load_hotspots(building_id):
        tag_terms = {_normalize_token(tag) for tag in hotspot.tags}
        name_terms = _tokenize(hotspot.name)
        id_terms = _tokenize(hotspot.id.replace("_", " "))
        hotspot_terms = tag_terms | name_terms | id_terms

        overlap = sorted((terms & hotspot_terms) - {""})
        phrase_hit = hotspot.name.lower() in query.lower() or hotspot.id.replace("_", " ") in normalized_query

        if not overlap and not phrase_hit:
            continue

        overlap_count = len(overlap)
        if phrase_hit or overlap_count >= 3:
            confidence = 0.9
        elif overlap_count == 2:
            confidence = 0.82
        else:
            confidence = 0.72

        confidence = min(0.95, confidence + min(0.05, hotspot.priority * 0.004))
        scored.append((confidence, overlap_count, hotspot, overlap))

    scored.sort(key=lambda row: (row[0], row[1], row[2].priority), reverse=True)

    ranked = []
    for confidence, _, hotspot, overlap in scored[:3]:
        overlap_text = ", ".join(overlap[:4]) if overlap else "name/phrase match"
        ranked.append(
            {
                "id": hotspot.id,
                "confidence": confidence,
                "reason": f"Matched query to hotspot terms: {overlap_text}.",
            }
        )
    return ranked
