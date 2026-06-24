"""Curated advertising knowledge retrieval for the ad-video pipeline.

This module is deliberately local and deterministic by default. It gives the
agent a professional producer knowledge layer without turning Video Production Buddy into
an opaque Python orchestrator: directors still decide how to apply guidance,
while this code loads cards, validates their contract, and ranks likely matches.
"""

from __future__ import annotations

import json
import hashlib
import math
import re
from collections import Counter
from pathlib import Path
from typing import Any, Protocol

import jsonschema

from schemas.artifacts import load_strict_json_object


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CARD_DIR = ROOT / "knowledge" / "ad-video"
CARD_SCHEMA_PATH = ROOT / "schemas" / "knowledge" / "ad_video_knowledge_card.schema.json"
DEFAULT_TOP_K = 6
MIN_TOP_K = 1
MAX_TOP_K = 20

# Per-field BM25 boost weights. Higher weight = stronger influence on retrieval
# ranking. Domain and keywords are curated high-precision signals; avoid_when
# and failure_patterns are weaker positive matches but help distinguish cards.
FIELD_WEIGHTS: dict[str, float] = {
    "domain": 3.0,
    "keywords": 2.5,
    "apply_when": 2.0,
    "principles": 1.5,
    "execution_techniques": 1.0,
    "summary": 1.0,
    "avoid_when": 0.5,
    "failure_patterns": 0.5,
}

# Boosts applied *after* BM25 scoring when the card's metadata matches query
# inputs directly. These reward structural relevance on top of text similarity.
TARGET_DOMAIN_BOOST = 2.0
TARGET_DOWNSTREAM_BOOST = 0.75
TARGET_KEYWORD_BOOST = 0.5


class EmbeddingScorer(Protocol):
    """Protocol for pluggable embedding-based card scoring."""

    def __call__(self, cards: list[dict[str, Any]], query: str) -> list[float]: ...

    @property
    def model_name(self) -> str: ...


def _load_card_schema() -> dict[str, Any]:
    return load_strict_json_object(CARD_SCHEMA_PATH, context="ad knowledge card schema")


def _content_hash(card: dict[str, Any]) -> str:
    payload = {key: value for key, value in card.items() if key != "content_hash"}
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )
    return "sha256:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def load_ad_knowledge_cards(card_dir: Path | str | None = None) -> list[dict[str, Any]]:
    """Load and schema-validate curated ad-video knowledge cards."""
    directory = Path(card_dir) if card_dir is not None else DEFAULT_CARD_DIR
    schema = _load_card_schema()
    cards: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    for path in sorted(directory.glob("*.json")):
        card = load_strict_json_object(path, context=f"ad knowledge card {path.name}")
        jsonschema.validate(instance=card, schema=schema)
        expected_hash = _content_hash(card)
        if card.get("content_hash") != expected_hash:
            raise ValueError(
                f"ad knowledge card {path.name} content_hash mismatch: "
                f"expected {expected_hash}, got {card.get('content_hash')}"
            )

        card_id = card["card_id"]
        if card_id in seen_ids:
            raise ValueError(f"Duplicate ad knowledge card_id: {card_id}")
        seen_ids.add(card_id)
        cards.append(card)

    if not cards:
        raise ValueError(f"No ad knowledge cards found in {directory}")
    return cards


def _tokens(value: Any) -> list[str]:
    return re.findall(r"[a-z0-9]+", str(value or "").lower())


def _field_tokens(card: dict[str, Any], field: str) -> list[str]:
    """Extract tokens from a specific card field for field-weighted scoring."""
    if field == "domain":
        return _tokens(card.get("domain", ""))

    value = card.get(field)
    if value is None:
        return []
    if isinstance(value, list):
        return _tokens(" ".join(str(item) for item in value))
    return _tokens(str(value))


def _query_text(inputs: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in (
        "product_category",
        "platform",
        "audience",
        "objectives",
        "validation_targets",
        "brief",
        "product",
    ):
        raw = inputs.get(key)
        if isinstance(raw, str):
            parts.append(raw)
        elif isinstance(raw, list):
            parts.extend(str(item) for item in raw)
    return " ".join(parts)


def _target_terms(inputs: dict[str, Any]) -> set[str]:
    terms: set[str] = set()
    for value in inputs.get("validation_targets", []) or []:
        normalized = str(value).strip().lower().replace("-", "_").replace(" ", "_")
        if normalized:
            terms.add(normalized)
            terms.update(_tokens(normalized))
    for value in inputs.get("objectives", []) or []:
        terms.update(_tokens(value))
    terms.update(_tokens(inputs.get("platform")))
    return terms


def _bm25_score_field(
    query_terms: list[str],
    field_tokens: list[str],
    doc_freq: Counter[str],
    num_docs: int,
    avg_field_len: float,
    k1: float = 1.2,
    b: float = 0.75,
) -> float:
    """Score a single card field against query terms using BM25."""
    if not query_terms or not field_tokens:
        return 0.0

    tf = Counter(field_tokens)
    field_len = max(len(field_tokens), 1)
    score = 0.0

    for term in query_terms:
        if tf[term] == 0:
            continue
        idf = math.log((num_docs - doc_freq[term] + 0.5) / (doc_freq[term] + 0.5) + 1.0)
        denom = tf[term] + k1 * (1 - b + b * field_len / max(avg_field_len, 1))
        score += idf * (tf[term] * (k1 + 1)) / denom

    return score


def _compute_field_doc_freq(
    cards: list[dict[str, Any]], field: str,
) -> tuple[Counter[str], float]:
    """Compute document frequency and average length for a single field."""
    doc_freq: Counter[str] = Counter()
    total_len = 0

    for card in cards:
        tokens = _field_tokens(card, field)
        doc_freq.update(set(tokens))
        total_len += len(tokens)

    avg_len = total_len / max(len(cards), 1)
    return doc_freq, avg_len


def _bm25_scores(cards: list[dict[str, Any]], query: str, inputs: dict[str, Any]) -> list[float]:
    """Score cards using field-weighted BM25 plus target boosts."""
    query_terms = _tokens(query)
    if not query_terms:
        return [0.0 for _ in cards]

    num_docs = len(cards)
    scores: list[float] = []

    # Pre-compute per-field document frequencies and average lengths.
    field_stats: dict[str, tuple[Counter[str], float]] = {}
    for field in FIELD_WEIGHTS:
        field_stats[field] = _compute_field_doc_freq(cards, field)

    targets = _target_terms(inputs)

    for card in cards:
        field_score = 0.0

        for field, weight in FIELD_WEIGHTS.items():
            doc_freq, avg_len = field_stats[field]
            tokens = _field_tokens(card, field)
            raw = _bm25_score_field(query_terms, tokens, doc_freq, num_docs, avg_len)
            field_score += raw * weight

        # Structural boosts: reward cards whose metadata aligns with the query
        # intent even when the text match is partial.
        domain = str(card.get("domain") or "").lower()
        downstream = {str(item).lower() for item in card.get("downstream_targets", [])}
        keywords = {str(item).lower() for item in card.get("keywords", [])}

        if domain in targets:
            field_score += TARGET_DOMAIN_BOOST
        if downstream.intersection(targets):
            field_score += TARGET_DOWNSTREAM_BOOST
        if any(token in " ".join(keywords) for token in targets):
            field_score += TARGET_KEYWORD_BOOST

        scores.append(field_score)

    return scores


def _normalize_ranked(cards: list[dict[str, Any]], scores: list[float], top_k: int) -> list[dict[str, Any]]:
    paired = [
        (card, score)
        for card, score in zip(cards, scores)
        if score > 0
    ]
    paired.sort(key=lambda item: (-item[1], item[0]["card_id"]))
    if not paired:
        paired = [(card, 1.0) for card in cards[:top_k]]

    max_score = max(score for _, score in paired) or 1.0
    out: list[dict[str, Any]] = []
    for card, score in paired[:top_k]:
        item = {
            "card_id": card["card_id"],
            "domain": card["domain"],
            "source_ref": f"knowledge_alignment:{card['card_id']}",
            "summary": card["summary"],
            "principles": card["principles"],
            "relevance_score": round(max(0.01, min(score / max_score, 1.0)), 3),
            "why_relevant": _why_relevant(card),
            "avoid_when": card["avoid_when"],
            "downstream_targets": card["downstream_targets"],
            "failure_patterns": card["failure_patterns"],
            "execution_techniques": card["execution_techniques"],
        }
        cross_domain_notes = card.get("cross_domain_notes")
        if isinstance(cross_domain_notes, list) and cross_domain_notes:
            item["cross_domain_notes"] = cross_domain_notes
        out.append(item)
    return out


def _why_relevant(card: dict[str, Any]) -> str:
    apply_when = card.get("apply_when") or []
    if apply_when:
        return apply_when[0]
    return card["summary"]


def _recommendations(cards_by_id: dict[str, dict[str, Any]], retrieved: list[dict[str, Any]]) -> list[dict[str, Any]]:
    recommendations: list[dict[str, Any]] = []
    for item in retrieved:
        card = cards_by_id[item["card_id"]]
        recommendations.append(
            {
                "card_id": card["card_id"],
                "target": card["downstream_targets"][0],
                "recommendation": card["principles"][0],
                "confidence": "producer-doctrine",
            }
        )
    return recommendations


def _contraindications(cards_by_id: dict[str, dict[str, Any]], retrieved: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in retrieved:
        card = cards_by_id[item["card_id"]]
        out.append(
            {
                "card_id": card["card_id"],
                "avoid_when": card["avoid_when"][0],
                "reason": "Apply only when the brief and truth contract allow it.",
            }
        )
    return out


def _normalized_target(value: Any) -> str:
    return str(value).strip().lower().replace("-", "_").replace(" ", "_")


def _retrieved_targets(item: dict[str, Any]) -> set[str]:
    targets = {_normalized_target(item.get("domain"))}
    for target in item.get("downstream_targets", []) or []:
        normalized = _normalized_target(target)
        if normalized:
            targets.add(normalized)
            targets.update(_tokens(normalized))
    return {target for target in targets if target}


def _gaps(inputs: dict[str, Any], retrieved: list[dict[str, Any]]) -> list[str]:
    retrieved_targets = {
        target
        for item in retrieved
        for target in _retrieved_targets(item)
    }
    gaps: list[str] = []
    for target in inputs.get("validation_targets", []) or []:
        normalized = _normalized_target(target)
        if normalized and normalized not in retrieved_targets:
            gaps.append(f"No direct curated card matched validation target: {normalized}")
    return gaps


def _coerce_top_k(value: Any) -> int:
    """Validate retrieval depth against the tool input contract."""
    if value is None:
        return DEFAULT_TOP_K
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(
            f"top_k must be an integer between {MIN_TOP_K} and {MAX_TOP_K}"
        )
    top_k = value
    if not MIN_TOP_K <= top_k <= MAX_TOP_K:
        raise ValueError(
            f"top_k must be an integer between {MIN_TOP_K} and {MAX_TOP_K}"
        )
    return top_k


def retrieve_ad_knowledge(
    inputs: dict[str, Any],
    *,
    cards: list[dict[str, Any]] | None = None,
    embedding_scorer: EmbeddingScorer | None = None,
) -> dict[str, Any]:
    """Retrieve professional ad-video knowledge for the current brief.

    ``backend="auto"`` and ``backend="bm25"`` use deterministic field-weighted
    lexical scoring. ``backend="embedding"`` or ``backend="hybrid"`` can use an
    injected scorer; without one they fall back to BM25 with an explicit warning
    so the pipeline remains local and testable.
    """
    cards = list(cards) if cards is not None else load_ad_knowledge_cards()
    cards_by_id = {card["card_id"]: card for card in cards}
    backend = str(inputs.get("backend") or "auto").lower()
    top_k = _coerce_top_k(inputs.get("top_k"))
    query = _query_text(inputs)
    warnings: list[str] = []

    if backend in {"embedding", "hybrid"} and embedding_scorer is not None:
        raw_scores = embedding_scorer(cards, query)
        backend_used = "embedding" if backend == "embedding" else "hybrid"
    else:
        if backend in {"embedding", "hybrid"}:
            warnings.append("Embedding backend is not configured; fell back to deterministic BM25 retrieval.")
        raw_scores = _bm25_scores(cards, query, inputs)
        backend_used = "bm25"

    retrieved = _normalize_ranked(cards, raw_scores, top_k)
    return {
        "retrieval_backend": backend_used,
        "warnings": warnings,
        "cards_used": retrieved,
        "application_recommendations": _recommendations(cards_by_id, retrieved),
        "contraindications": _contraindications(cards_by_id, retrieved),
        "gaps": _gaps(inputs, retrieved),
    }
