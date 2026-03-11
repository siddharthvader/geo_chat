#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
EVAL_PATH = ROOT / "data" / "evals" / "questions.json"
REPORT_PATH = ROOT / "data" / "evals" / "report.md"
API_BASE = os.environ.get("API_BASE", "http://localhost:8000")


def run_case(question: dict) -> dict:
    payload = {"session_id": "eval-session", "message": question["q"]}
    if question.get("building_id"):
        payload["building_id"] = question["building_id"]
    response = requests.post(f"{API_BASE}/chat", json=payload, timeout=60)
    response.raise_for_status()
    body = response.json()

    returned_hotspots = [h["id"] for h in body.get("actions", {}).get("hotspots", [])]
    expected = set(question.get("expected_hotspots", []))
    hotspot_hit = int(bool(expected.intersection(returned_hotspots))) if expected else 1

    must_mentions = question.get("must_mention", [])
    answer = body.get("answer", "")
    must_hit = all(m.lower() in answer.lower() for m in must_mentions)

    return {
      "building_id": question.get("building_id", "palace_of_fine_arts"),
      "question": question["q"],
      "hotspot_hit": hotspot_hit,
      "has_citations": int(bool(body.get("citations"))),
      "must_mention_pass": int(must_hit),
      "returned_hotspots": returned_hotspots,
      "answer": answer,
    }


def main() -> None:
    cases = json.loads(EVAL_PATH.read_text(encoding="utf-8"))
    results = [run_case(case) for case in cases]

    total = len(results)
    hotspot_score = sum(r["hotspot_hit"] for r in results) / total
    citation_score = sum(r["has_citations"] for r in results) / total
    mention_score = sum(r["must_mention_pass"] for r in results) / total

    lines = []
    lines.append("# BuildingTalk Eval Report")
    lines.append("")
    lines.append(f"Generated: {datetime.now(timezone.utc).isoformat()}")
    lines.append("")
    lines.append(f"- Cases: {total}")
    lines.append(f"- Hotspot hit rate: {hotspot_score:.2f}")
    lines.append(f"- Citation presence: {citation_score:.2f}")
    lines.append(f"- Must-mention pass rate: {mention_score:.2f}")
    lines.append("")
    lines.append("## Per-question")
    lines.append("")

    for r in results:
        lines.append(f"### [{r['building_id']}] {r['question']}")
        lines.append(f"- hotspot_hit: {r['hotspot_hit']}")
        lines.append(f"- has_citations: {r['has_citations']}")
        lines.append(f"- must_mention_pass: {r['must_mention_pass']}")
        lines.append(f"- returned_hotspots: {', '.join(r['returned_hotspots']) or '(none)'}")
        lines.append(f"- answer: {r['answer'][:280]}")
        lines.append("")

    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {REPORT_PATH}")


if __name__ == "__main__":
    main()
