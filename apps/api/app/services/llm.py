from __future__ import annotations

import json
import logging
import re
from typing import Optional

from openai import OpenAI
from pydantic import BaseModel

from app.core.config import get_settings
from app.core.models import ChatResponse, Citation, HotspotAction, RetrievedChunk
from app.services.hotspots import rank_hotspots_by_query, summarize_hotspots_for_prompt

HOTSPOT_CONFIDENCE_MIN = 0.78
MIN_CONTEXT_SIGNAL_FOR_GROUNDED_ANSWER = 0.16
logger = logging.getLogger(__name__)


class StructuredLLMOutput(BaseModel):
    answer: str
    citations: list[Citation]
    hotspots: list[HotspotAction]


def _coerce_confidence(value: object) -> float:
    if isinstance(value, (int, float)):
        return max(0.0, min(1.0, float(value)))
    if isinstance(value, str):
        text = value.strip().lower()
        aliases = {
            "very high": 0.92,
            "high": 0.85,
            "medium": 0.72,
            "low": 0.58,
            "very low": 0.45,
        }
        if text in aliases:
            return aliases[text]
        if text.endswith("%"):
            try:
                return max(0.0, min(1.0, float(text[:-1]) / 100.0))
            except ValueError:
                return 0.72
        try:
            return max(0.0, min(1.0, float(text)))
        except ValueError:
            return 0.72
    return 0.72


def _coerce_output(payload: dict) -> StructuredLLMOutput:
    answer = str(payload.get("answer", "")).strip()
    if not answer:
        answer = "I can provide an architectural overview, but I need clearer context for specifics."

    citations: list[Citation] = []
    for citation in payload.get("citations", []):
        if not isinstance(citation, dict):
            continue
        title = str(citation.get("title", "")).strip()
        url = str(citation.get("url", "")).strip()
        snippet = str(citation.get("snippet", "")).strip()
        if not title or not url:
            continue
        citations.append(Citation(title=title, url=url, snippet=snippet[:280]))

    hotspots: list[HotspotAction] = []
    for hotspot in payload.get("hotspots", []):
        if not isinstance(hotspot, dict):
            continue
        hotspot_id = str(hotspot.get("id", "")).strip()
        if not hotspot_id:
            continue
        hotspots.append(
            HotspotAction(
                id=hotspot_id,
                confidence=_coerce_confidence(hotspot.get("confidence", 0.72)),
                reason=str(hotspot.get("reason", "")).strip() or None,
            )
        )

    return StructuredLLMOutput(answer=answer, citations=citations, hotspots=hotspots)


def _make_client() -> OpenAI:
    settings = get_settings()
    if settings.llm_provider == "openrouter":
        return OpenAI(
            api_key=settings.openrouter_api_key,
            base_url=settings.openai_base_url or "https://openrouter.ai/api/v1",
        )
    return OpenAI(api_key=settings.openai_api_key, base_url=settings.openai_base_url or None)


def _llm_available() -> bool:
    settings = get_settings()
    if settings.llm_provider == "openrouter":
        return bool(settings.openrouter_api_key)
    return bool(settings.openai_api_key)


def _build_context(chunks: list[RetrievedChunk], max_chars: int) -> str:
    parts: list[str] = []
    used = 0
    for idx, chunk in enumerate(chunks, start=1):
        excerpt = chunk.content.strip().replace("\n", " ")
        block = f"[{idx}] {chunk.title}\nURL: {chunk.url}\nEXCERPT: {excerpt}\n"
        if used + len(block) > max_chars:
            break
        parts.append(block)
        used += len(block)
    return "\n".join(parts)


def _tokenize(text: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9]+", text.lower()) if len(token) > 2}


def _estimate_context_signal(message: str, chunks: list[RetrievedChunk]) -> float:
    query_terms = _tokenize(message)
    if not query_terms or not chunks:
        return 0.0

    best = 0.0
    for chunk in chunks[:5]:
        chunk_terms = _tokenize(chunk.content[:2800])
        if not chunk_terms:
            continue
        overlap = len(query_terms.intersection(chunk_terms))
        signal = overlap / max(1, min(6, len(query_terms)))
        best = max(best, signal)
    return min(1.0, best)


def _merge_hotspots(
    message: str,
    ranked_hotspots: list[dict[str, object]],
    llm_hotspots: list[HotspotAction],
    building_id: Optional[str] = None,
) -> list[HotspotAction]:
    catalog = summarize_hotspots_for_prompt(building_id)
    catalog_ids = {item["id"] for item in catalog}
    catalog_terms: dict[str, set[str]] = {}
    for item in catalog:
        item_text = f"{item['id']} {item.get('name', '')} {' '.join(item.get('tags', []))}"
        catalog_terms[item["id"]] = _tokenize(item_text)
    query_terms = _tokenize(message)

    def has_query_support(hotspot_id: str) -> bool:
        return bool(query_terms.intersection(catalog_terms.get(hotspot_id, set())))

    merged: dict[str, HotspotAction] = {}

    for hotspot in ranked_hotspots:
        try:
            candidate = HotspotAction(
                id=str(hotspot["id"]),
                confidence=float(hotspot["confidence"]),
                reason=str(hotspot.get("reason", "")),
            )
        except Exception:
            continue
        if candidate.id in catalog_ids and candidate.confidence >= HOTSPOT_CONFIDENCE_MIN:
            merged[candidate.id] = candidate

    for candidate in llm_hotspots:
        if candidate.id not in catalog_ids or candidate.confidence < HOTSPOT_CONFIDENCE_MIN:
            continue
        if not has_query_support(candidate.id):
            continue
        current = merged.get(candidate.id)
        if current is None or candidate.confidence > current.confidence:
            merged[candidate.id] = candidate

    return sorted(merged.values(), key=lambda item: item.confidence, reverse=True)[:3]


def _invoke_llm(
    message: str,
    context: str,
    history: list[dict[str, str]],
    allow_model_knowledge: bool,
    client_context: Optional[str] = None,
    building_id: Optional[str] = None,
) -> StructuredLLMOutput:
    settings = get_settings()
    client = _make_client()
    hotspots = summarize_hotspots_for_prompt(building_id)

    context_mode = "grounded_plus_model_priors" if allow_model_knowledge else "grounded_only"
    citation_count_rule = "1-4" if context.strip() else "0-1"
    system = (
        "You are an architectural historian assistant. "
        "Prefer the provided context whenever it is relevant. "
        "If context is weak and model-priors mode is enabled, answer from general architectural/historical knowledge. "
        "The client_context field is UI-provided spatial orientation; use it for disambiguation but do not treat it as citable evidence. "
        "Always return valid JSON with keys: answer, citations, hotspots. "
        "citations entries must include title,url,snippet. "
        "hotspots entries must include id,confidence,reason. "
        "Choose up to 3 hotspot ids from the provided hotspot catalog only. "
        "Only include hotspots when location confidence is high."
    )

    user_payload = {
        "question": message,
        "conversation": history,
        "context": context,
        "client_context": client_context or "",
        "hotspot_catalog": hotspots,
        "rules": {
            "max_hotspots": 3,
            "context_mode": context_mode,
            "must_cite_provided_context_when_used": True,
            "citation_count": citation_count_rule,
        },
    }

    completion = client.chat.completions.create(
        model=settings.llm_model,
        temperature=0.2,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(user_payload)},
        ],
    )
    content = completion.choices[0].message.content or "{}"

    try:
        parsed = _coerce_output(json.loads(content))
    except json.JSONDecodeError:
        repair_prompt = (
            "Convert the following output into valid JSON with keys "
            "answer:string, citations:[{title,url,snippet}], hotspots:[{id,confidence,reason}]. "
            "Do not add markdown.\n\n"
            f"RAW:\n{content}"
        )
        repair = client.chat.completions.create(
            model=settings.llm_model,
            temperature=0,
            response_format={"type": "json_object"},
            messages=[{"role": "user", "content": repair_prompt}],
        )
        parsed = _coerce_output(json.loads(repair.choices[0].message.content or "{}"))

    return parsed


def _grounded_citations(citations: list[Citation], chunks: list[RetrievedChunk]) -> list[Citation]:
    if not citations:
        return []

    allowed_urls = {chunk.url for chunk in chunks if chunk.url}
    grounded: list[Citation] = []
    seen: set[str] = set()
    for citation in citations:
        if allowed_urls and citation.url not in allowed_urls:
            continue
        key = f"{citation.title}|{citation.url}"
        if key in seen:
            continue
        seen.add(key)
        grounded.append(citation)
    return grounded


def _fallback_citations(chunks: list[RetrievedChunk], max_items: int = 2) -> list[Citation]:
    citations: list[Citation] = []
    seen_urls: set[str] = set()
    for chunk in chunks:
        if not chunk.url or chunk.url in seen_urls:
            continue
        seen_urls.add(chunk.url)
        citations.append(Citation(title=chunk.title, url=chunk.url, snippet=chunk.content[:220].strip()))
        if len(citations) >= max_items:
            break
    return citations


def answer_question(
    message: str,
    chunks: list[RetrievedChunk],
    history: list[dict[str, str]],
    client_context: Optional[str] = None,
    building_id: Optional[str] = None,
) -> ChatResponse:
    settings = get_settings()
    ranked_hotspots = rank_hotspots_by_query(message, building_id)
    context_signal = _estimate_context_signal(message, chunks)
    allow_model_knowledge = not chunks or context_signal < 0.2

    if not _llm_available():
        citations = _fallback_citations(chunks, max_items=3)
        answer = (
            "I can map likely building locations, but no LLM API key is configured for generated answers. "
            "Set OPENAI_API_KEY or OPENROUTER_API_KEY."
        )
        if not citations:
            answer = (
                "I don’t have enough in the provided sources to answer confidently. "
                "Also, no LLM API key is configured for generated answers."
            )
        return ChatResponse(
            answer=answer,
            citations=citations,
            actions={"hotspots": _merge_hotspots(message, ranked_hotspots, [], building_id)},
        )

    context = _build_context(chunks, settings.max_context_chars) if chunks else ""
    if client_context:
        context = f"[Client Focus Context]\\n{client_context}\\n\\n{context}"

    try:
        parsed = _invoke_llm(
            message=message,
            context=context,
            history=history,
            allow_model_knowledge=allow_model_knowledge,
            client_context=client_context,
            building_id=building_id,
        )
        citations = _grounded_citations(parsed.citations, chunks)[:4]
        if not citations:
            citations = _fallback_citations(chunks, max_items=2)

        if not citations:
            return ChatResponse(
                answer="I don’t have enough in the provided sources to answer confidently.",
                citations=[],
                actions={"hotspots": []},
            )

        if context_signal < MIN_CONTEXT_SIGNAL_FOR_GROUNDED_ANSWER:
            return ChatResponse(
                answer="I don’t have enough in the provided sources to answer confidently.",
                citations=citations,
                actions={"hotspots": []},
            )

        actions = {"hotspots": _merge_hotspots(message, ranked_hotspots, parsed.hotspots, building_id)}
        return ChatResponse(answer=parsed.answer, citations=citations, actions=actions)
    except Exception as exc:
        logger.exception(
            "LLM invocation failed for provider=%s model=%s building_id=%s",
            settings.llm_provider,
            settings.llm_model,
            building_id or "",
        )
        # Fallback keeps product responsive if model call fails.
        citations = _fallback_citations(chunks, max_items=3)
        fallback_answer = (
            "I couldn’t complete model reasoning, but I can still suggest likely building areas."
            if not chunks
            else "I couldn’t complete model reasoning, but here are relevant sources I found."
        )
        if not citations:
            fallback_answer = "I don’t have enough in the provided sources to answer confidently."
        return ChatResponse(
            answer=fallback_answer,
            citations=citations,
            actions={"hotspots": _merge_hotspots(message, ranked_hotspots, [], building_id)},
        )
