from __future__ import annotations

import json
from functools import lru_cache
from typing import Optional

from app.core.config import get_settings
from app.core.models import Building

DEFAULT_BUILDING_ID = "palace_of_fine_arts"


@lru_cache
def _raw_buildings() -> list[dict]:
    path = get_settings().resolved_buildings_path
    if path.exists():
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return data

    # Fallback for older single-building setups.
    return [
        {
            "id": DEFAULT_BUILDING_ID,
            "name": "Palace of Fine Arts",
            "location": "San Francisco, CA",
            "description": "1915 exposition structure with rotunda, colonnade, and lagoon axis.",
            "model_url": "/models/palace.glb",
            "model_attribution": "Azad Balabanian via Sketchfab",
            "model_source_url": "https://sketchfab.com/3d-models/palace-of-fine-arts-san-francisco-ca-a5e91dea48804b6c901d64483eb25b81",
            "model_license": "CC BY 4.0",
            "hotspots_file": get_settings().hotspots_file,
            "suggested_prompts": [
                "What are the weeping ladies?",
                "Why does the site look like a ruin?",
                "When was the Palace reconstructed?",
            ],
        }
    ]


@lru_cache
def _building_map() -> dict[str, dict]:
    mapping: dict[str, dict] = {}
    for item in _raw_buildings():
        building_id = item.get("id")
        if not building_id:
            continue
        mapping[building_id] = item
    return mapping


def get_default_building_id() -> str:
    if DEFAULT_BUILDING_ID in _building_map():
        return DEFAULT_BUILDING_ID
    ids = list(_building_map().keys())
    return ids[0] if ids else DEFAULT_BUILDING_ID


def resolve_building_id(building_id: Optional[str]) -> str:
    if building_id and building_id in _building_map():
        return building_id
    return get_default_building_id()


def get_building_record(building_id: Optional[str]) -> dict:
    resolved = resolve_building_id(building_id)
    return _building_map()[resolved]


def get_hotspots_file_for_building(building_id: Optional[str]) -> str:
    record = get_building_record(building_id)
    return str(record.get("hotspots_file") or get_settings().hotspots_file)


def list_buildings() -> list[Building]:
    out: list[Building] = []
    for item in _raw_buildings():
        try:
            out.append(
                Building(
                    id=item["id"],
                    name=item["name"],
                    location=item.get("location", ""),
                    description=item.get("description", ""),
                    modelUrl=item.get("model_url", "/models/palace.glb"),
                    suggestedPrompts=item.get("suggested_prompts", []),
                    modelAttribution=item.get("model_attribution"),
                    modelSourceUrl=item.get("model_source_url"),
                    modelLicense=item.get("model_license"),
                )
            )
        except Exception:
            continue
    return out
