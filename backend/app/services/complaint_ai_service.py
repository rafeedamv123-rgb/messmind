import json

import httpx

from app.core.config import get_settings


def analyze_complaint(text: str) -> dict:
    settings = get_settings()
    if not settings.ai_complaint_url:
        return {
            "ai_unavailable": True,
            "ai_summary": None,
            "ai_topics": [],
            "fallback_summary": _rule_based_topics(text),
        }
    try:
        headers = {}
        if settings.ai_complaint_api_key:
            headers["Authorization"] = f"Bearer {settings.ai_complaint_api_key}"
        with httpx.Client(timeout=8.0) as client:
            resp = client.post(
                settings.ai_complaint_url,
                json={"text": text},
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()
            return {
                "ai_unavailable": False,
                "ai_summary": data.get("summary"),
                "ai_topics": data.get("topics", []),
                "fallback_summary": None,
            }
    except Exception:
        return {
            "ai_unavailable": True,
            "ai_summary": None,
            "ai_topics": [],
            "fallback_summary": _rule_based_topics(text),
        }


def _rule_based_topics(text: str) -> str:
    lowered = text.lower()
    topics = []
    keywords = {
        "spicy": "taste/spice",
        "bland": "taste",
        "oily": "texture/oil",
        "quality": "cooking quality",
        "cold": "temperature",
        "portion": "portion size",
    }
    for key, label in keywords.items():
        if key in lowered:
            topics.append(label)
    if not topics:
        topics.append("general feedback")
    return json.dumps(topics)
