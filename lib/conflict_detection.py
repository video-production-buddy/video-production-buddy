"""Trend-knowledge conflict detection for ad-video pipeline.

Cross-checks selected trends against selected professional knowledge cards
to catch cases where a trendy visual/pacing idea contradicts established
professional principles. The bible-director calls this during trend selection
(Step 4) so conflicts surface before the bible is locked.
"""

from __future__ import annotations

from typing import Any


def _lower(value: Any) -> str:
    return str(value or "").strip().lower()


def _trend_visual_instruction(trend_alignment: dict[str, Any]) -> str:
    scene_usage = trend_alignment.get("scene_usage") or {}
    if isinstance(scene_usage, dict):
        return str(scene_usage.get("visual_or_pacing_instruction") or "").strip()
    return ""


def _card_avoid_conditions(card: dict[str, Any]) -> list[str]:
    conditions: list[str] = []
    for item in card.get("avoid_when") or []:
        if isinstance(item, str) and item.strip():
            conditions.append(item.strip().lower())
    return conditions


def _card_do_not_overapply(knowledge_alignment: dict[str, Any]) -> list[str]:
    conditions: list[str] = []
    for item in knowledge_alignment.get("do_not_overapply") or []:
        if isinstance(item, str) and item.strip():
            conditions.append(item.strip().lower())
    return conditions


def _text_overlaps(text_a: str, text_b: str, min_word_overlap: int = 3) -> bool:
    """Check if two short texts share enough significant words to indicate a conflict.

    Uses word-level overlap after normalizing. This is intentionally conservative:
    single shared words like "visual" or "product" don't indicate conflict.
    """
    words_a = {w for w in _lower(text_a).split() if len(w) > 3}
    words_b = {w for w in _lower(text_b).split() if len(w) > 3}
    return len(words_a & words_b) >= min_word_overlap


def check_trend_knowledge_conflicts(
    trend_alignments: list[dict[str, Any]],
    knowledge_cards: list[dict[str, Any]],
    knowledge_alignments: list[dict[str, Any]],
) -> dict[str, Any]:
    """Cross-check selected trends against selected professional knowledge cards.

    Returns ``{ok, conflicts[], summary}`` where each conflict entry identifies
    the trend and card that disagree, the specific condition violated, and a
    recommendation (typically: follow the professional principle).

    ``trend_alignments`` comes from ``production_bible.intelligence.trend_alignment.alignments[]``.
    ``knowledge_cards`` is the full card objects for the selected knowledge cards.
    ``knowledge_alignments`` comes from ``production_bible.intelligence.knowledge_alignment.alignments[]``.
    """
    conflicts: list[dict[str, Any]] = []

    cards_by_id = {
        card["card_id"]: card
        for card in knowledge_cards
        if isinstance(card, dict) and "card_id" in card
    }

    for trend_entry in trend_alignments:
        if not isinstance(trend_entry, dict):
            continue

        trend_id = str(trend_entry.get("trend_id") or trend_entry.get("signal") or "unknown")
        trend_instruction = _trend_visual_instruction(trend_entry)

        for k_entry in knowledge_alignments:
            if not isinstance(k_entry, dict):
                continue

            card_id = str(k_entry.get("card_id") or "")
            card = cards_by_id.get(card_id)
            if not card:
                continue

            # Check trend instruction against card's avoid_when conditions.
            for avoid_condition in _card_avoid_conditions(card):
                if not trend_instruction:
                    continue
                if _text_overlaps(trend_instruction, avoid_condition, min_word_overlap=2):
                    conflicts.append({
                        "kind": "trend_knowledge_conflict",
                        "trend_id": trend_id,
                        "card_id": card_id,
                        "conflict_type": "trend_matches_avoid_condition",
                        "trend_instruction": trend_instruction[:200],
                        "card_avoid_condition": avoid_condition[:200],
                        "recommendation": (
                            f"Follow the professional principle from {card_id} and "
                            f"exclude or reframe this trend application."
                        ),
                    })

            # Check trend instruction against alignment's do_not_overapply.
            for overapply in _card_do_not_overapply(k_entry):
                if not trend_instruction:
                    continue
                if _text_overlaps(trend_instruction, overapply, min_word_overlap=2):
                    conflicts.append({
                        "kind": "trend_knowledge_overapply_conflict",
                        "trend_id": trend_id,
                        "card_id": card_id,
                        "conflict_type": "trend_triggers_overapply_guard",
                        "trend_instruction": trend_instruction[:200],
                        "card_overapply_condition": overapply[:200],
                        "recommendation": (
                            f"This trend application would overapply the {card_id} principle. "
                            f"Reduce scope or exclude this trend."
                        ),
                    })

    return {
        "ok": not conflicts,
        "conflicts": conflicts,
        "summary": {
            "trends_checked": len(trend_alignments),
            "knowledge_cards_checked": len(knowledge_alignments),
            "conflicts_found": len(conflicts),
        },
    }
