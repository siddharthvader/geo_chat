from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    session_id: str
    message: str
    building_id: Optional[str] = None
    client_context: Optional[str] = None


class Citation(BaseModel):
    title: str
    url: str
    snippet: str


class HotspotAction(BaseModel):
    id: str
    confidence: float = Field(ge=0, le=1)
    reason: Optional[str] = None


class ChatResponse(BaseModel):
    answer: str
    citations: list[Citation]
    actions: dict[str, list[HotspotAction]]


class Hotspot(BaseModel):
    id: str
    name: str
    description: str
    tags: list[str] = Field(default_factory=list)
    bbox: Optional[dict[str, Any]] = None
    camera: Optional[dict[str, Any]] = None
    meshNames: list[str] = Field(default_factory=list)
    priority: int = 0


class Building(BaseModel):
    id: str
    name: str
    location: str
    description: str
    modelUrl: str
    suggestedPrompts: list[str] = Field(default_factory=list)
    modelAttribution: Optional[str] = None
    modelSourceUrl: Optional[str] = None
    modelLicense: Optional[str] = None


class RetrievedChunk(BaseModel):
    chunk_id: str
    title: str
    url: str
    content: str
    metadata: dict = Field(default_factory=dict)
