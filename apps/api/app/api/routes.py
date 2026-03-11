from __future__ import annotations

from fastapi import APIRouter, Query
from typing import Optional

from app.core.models import Building, ChatRequest, ChatResponse, Hotspot
from app.services.buildings import list_buildings, resolve_building_id
from app.services.hotspots import load_hotspots
from app.services.llm import answer_question
from app.services.retrieval import retrieve
from app.services.sessions import session_memory

router = APIRouter()


@router.get("/buildings", response_model=list[Building])
def get_buildings() -> list[Building]:
    return list_buildings()


@router.get("/hotspots", response_model=list[Hotspot])
def get_hotspots(building_id: Optional[str] = Query(default=None)) -> list[Hotspot]:
    return load_hotspots(building_id)


@router.post("/chat", response_model=ChatResponse)
def chat(body: ChatRequest) -> ChatResponse:
    building_id = resolve_building_id(body.building_id)
    memory_key = f"{body.session_id}:{building_id}"
    session_history = session_memory.get_turns(memory_key)
    try:
        chunks = retrieve(body.message, building_id=building_id)
    except Exception:
        chunks = []
    response = answer_question(
        body.message,
        chunks,
        session_history,
        body.client_context,
        building_id,
    )

    session_memory.add_turn(memory_key, "user", body.message)
    session_memory.add_turn(memory_key, "assistant", response.answer)
    return response
