"""Provider and production path scoring engine.

Replaces naive "first available provider" selection with weighted
multi-dimensional scoring. Every provider choice should be explainable —
not just "it was available."

Scores are normalized 0-1. Higher is better.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict, field
import math
import re
from typing import Any

from tools.status_utils import safe_tool_info, safe_tool_status


# ---------------------------------------------------------------------------
# Provider Score
# ---------------------------------------------------------------------------

@dataclass
class ProviderScore:
    """Scored evaluation of a provider against a specific task context."""

    tool_name: str
    provider: str
    task_fit: float = 0.0       # 0-1: best fit for this exact asset class
    output_quality: float = 0.0  # 0-1: expected fidelity for the brief
    control: float = 0.0        # 0-1: reference/style directability
    reliability: float = 0.0    # 0-1: runtime confidence
    cost_efficiency: float = 0.0  # 0-1: quality per dollar
    latency: float = 0.0        # 0-1: acceptable turnaround
    continuity: float = 0.0     # 0-1: fits already locked decisions

    @property
    def weighted_score(self) -> float:
        task_fit = _score_value(self.task_fit, 0.0)
        output_quality = _score_value(self.output_quality, 0.0)
        control = _score_value(self.control, 0.0)
        reliability = _score_value(self.reliability, 0.0)
        cost_efficiency = _score_value(self.cost_efficiency, 0.0)
        latency = _score_value(self.latency, 0.0)
        continuity = _score_value(self.continuity, 0.0)
        return (
            task_fit * 0.30
            + output_quality * 0.20
            + control * 0.15
            + reliability * 0.15
            + cost_efficiency * 0.10
            + latency * 0.05
            + continuity * 0.05
        )

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        for key in (
            "task_fit",
            "output_quality",
            "control",
            "reliability",
            "cost_efficiency",
            "latency",
            "continuity",
        ):
            d[key] = _score_value(d.get(key), 0.0)
        d["weighted_score"] = self.weighted_score
        return d

    def explain(self) -> str:
        """Human-readable explanation of this score."""
        payload = self.to_dict()
        parts = [f"{self.tool_name} ({self.provider}): {payload['weighted_score']:.2f}"]
        top = sorted(
            [
                ("task_fit", payload["task_fit"], 0.30),
                ("output_quality", payload["output_quality"], 0.20),
                ("control", payload["control"], 0.15),
                ("reliability", payload["reliability"], 0.15),
                ("cost_efficiency", payload["cost_efficiency"], 0.10),
                ("latency", payload["latency"], 0.05),
                ("continuity", payload["continuity"], 0.05),
            ],
            key=lambda x: x[1] * x[2],
            reverse=True,
        )
        for name, val, weight in top[:3]:
            parts.append(f"  {name}={val:.2f} (w={weight})")
        return "\n".join(parts)


# ---------------------------------------------------------------------------
# Production Path Score
# ---------------------------------------------------------------------------

@dataclass
class ProductionPathScore:
    """Scored evaluation of an entire production path."""

    path_label: str
    delivery_fit: float = 0.0
    quality_fit: float = 0.0
    capability_confidence: float = 0.0
    fallback_integrity: float = 0.0
    budget_fit: float = 0.0
    speed_fit: float = 0.0
    controllability: float = 0.0
    consistency_fit: float = 0.0

    @property
    def weighted_score(self) -> float:
        delivery_fit = _score_value(self.delivery_fit, 0.0)
        quality_fit = _score_value(self.quality_fit, 0.0)
        capability_confidence = _score_value(self.capability_confidence, 0.0)
        fallback_integrity = _score_value(self.fallback_integrity, 0.0)
        budget_fit = _score_value(self.budget_fit, 0.0)
        speed_fit = _score_value(self.speed_fit, 0.0)
        controllability = _score_value(self.controllability, 0.0)
        consistency_fit = _score_value(self.consistency_fit, 0.0)
        return (
            delivery_fit * 0.25
            + quality_fit * 0.20
            + capability_confidence * 0.15
            + fallback_integrity * 0.10
            + budget_fit * 0.10
            + speed_fit * 0.08
            + controllability * 0.07
            + consistency_fit * 0.05
        )

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        for key in (
            "delivery_fit",
            "quality_fit",
            "capability_confidence",
            "fallback_integrity",
            "budget_fit",
            "speed_fit",
            "controllability",
            "consistency_fit",
        ):
            d[key] = _score_value(d.get(key), 0.0)
        d["weighted_score"] = self.weighted_score
        return d


# ---------------------------------------------------------------------------
# Scoring Functions
# ---------------------------------------------------------------------------

def _keyword_overlap(set_a: set[str], set_b: set[str]) -> float:
    """Overlap coefficient between two keyword sets.

    Uses |A ∩ B| / min(|A|, |B|) rather than Jaccard. Jaccard over-penalizes
    tools whose best_for describes many strengths — a premium provider with
    seven rich bullets ends up with a smaller Jaccard than a narrowly-scoped
    provider with one bullet, even when the premium provider fully covers the
    intent. Overlap coefficient answers the relevant question: "is the intent
    a subset of what this tool advertises?" which is what we actually care
    about for provider scoring.
    """
    if not set_a or not set_b:
        return 0.0
    a = {s.lower().strip() for s in set_a}
    b = {s.lower().strip() for s in set_b}
    intersection = len(a & b)
    smaller = min(len(a), len(b))
    return intersection / smaller if smaller > 0 else 0.0


# Semantic synonym clusters: when intent says "cinematic" and tool says
# "film" or "movie", that's a match even without literal keyword overlap.
_SYNONYM_CLUSTERS: list[set[str]] = [
    {"cinematic", "film", "movie", "trailer", "dramatic", "epic"},
    {"explainer", "educational", "tutorial", "teaching", "lesson"},
    {"corporate", "business", "professional", "enterprise"},
    {"social", "tiktok", "instagram", "reels", "shorts", "viral"},
    {"animation", "animated", "motion-graphics", "motion", "kinetic"},
    {"pixar", "animation", "animated", "stylized", "storybook", "character"},
    {"realistic", "photorealistic", "lifelike", "natural"},
    {"stock", "footage", "b-roll", "library"},
    {"avatar", "presenter", "talking-head", "spokesperson"},
    {"voiceover", "narration", "speech", "voice"},
    {"music", "soundtrack", "background-music", "score", "ambient"},
]

_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9+._-]*")
_GENERATED_VISUAL_TERMS = {
    "animated",
    "animation",
    "anime",
    "cartoon",
    "character",
    "cinematic",
    "concept",
    "fantasy",
    "ghibli",
    "illustration",
    "pixar",
    "render",
    "scifi",
    "story",
    "stylized",
    "surreal",
}
_STOCK_VISUAL_TERMS = {
    "b-roll",
    "footage",
    "library",
    "stock",
}
_REFERENCE_TERMS = {
    "character",
    "consistency",
    "identity",
    "preserve",
    "product",
    "reference",
    "subject",
    "wardrobe",
}
_IMAGE_EDIT_TERMS = {
    "combine",
    "composite",
    "edit",
    "merge",
    "modify",
    "repaint",
    "replace",
    "style-transfer",
    "transfer",
}


def _tokenize_text(value: str) -> list[str]:
    return _TOKEN_RE.findall((value or "").lower())

def _expand_synonyms(words: set[str]) -> set[str]:
    """Expand a word set with synonyms from known clusters."""
    expanded = set(words)
    for cluster in _SYNONYM_CLUSTERS:
        if expanded & cluster:
            expanded |= cluster
    return expanded


def _compute_task_fit(
    best_for: set[str],
    intent: str,
    style_keywords: set[str],
) -> float:
    """Score how well a tool's best_for matches the task intent and style.

    Uses synonym expansion and a real tokenizer so that semantic near-misses
    (e.g. "cinematic" vs "film") and punctuation-adjacent tokens (e.g.
    "trailers," vs "trailer") still score well, not just literal whitespace
    splits.
    """
    if not best_for:
        return 0.3  # Unknown capability — modest default

    intent_words = _expand_synonyms(set(_tokenize_text(intent)))
    best_for_words: set[str] = set()
    for desc in best_for:
        best_for_words.update(_tokenize_text(desc))
    best_for_words = _expand_synonyms(best_for_words)

    intent_score = _keyword_overlap(intent_words, best_for_words)

    style_expanded = _expand_synonyms({kw.lower() for kw in style_keywords})
    style_score = _keyword_overlap(style_expanded, best_for_words)

    return min(1.0, intent_score * 0.7 + style_score * 0.3 + 0.1)


def _compute_control(supports: dict[str, Any]) -> float:
    """Score controllability from the supports dict.

    Features are weighted by creative impact — controlnet and reference_image
    are worth more than seed or aspect_ratio.
    """
    # (feature_name, weight) — higher weight = more creative control
    control_features = [
        ("controlnet", 2.0),
        ("reference_image", 1.8),
        ("image_to_video", 1.6),
        ("style_transfer", 1.5),
        ("inpainting", 1.5),
        ("img2img", 1.3),
        ("negative_prompt", 1.0),
        ("custom_size", 0.8),
        ("aspect_ratio", 0.7),
        ("seed", 0.5),
    ]
    if not supports:
        return 0.3
    total_weight = sum(w for _, w in control_features)
    earned = sum(w for f, w in control_features if supports.get(f))
    return min(1.0, earned / (total_weight * 0.5))


def _compute_cost_efficiency(
    estimated_cost: float,
    budget_remaining: float | None,
) -> float:
    """Score cost efficiency. Free is 1.0, over-budget is 0.0."""
    if estimated_cost <= 0:
        return 1.0
    if budget_remaining is not None and budget_remaining <= 0:
        return 0.0
    if budget_remaining is not None:
        ratio = estimated_cost / budget_remaining
        if ratio > 0.5:
            return 0.1
        if ratio > 0.2:
            return 0.5
        return 0.8
    # No budget info — use absolute cost heuristic
    if estimated_cost < 0.05:
        return 0.9
    if estimated_cost < 0.20:
        return 0.7
    if estimated_cost < 1.00:
        return 0.5
    return 0.3


def _finite_float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(parsed):
        return None
    return parsed


def _score_value(value: Any, default: float) -> float:
    parsed = _finite_float(value)
    if parsed is None:
        return default
    return min(1.0, max(0.0, parsed))


def _compute_continuity(
    provider: str,
    locked_providers: set[str],
) -> float:
    """Score how well this provider fits already-locked decisions."""
    if not locked_providers:
        return 0.5  # No prior context
    if provider in locked_providers:
        return 0.9  # Same provider = likely consistent style
    return 0.4  # Different provider = possible style break


def normalize_task_context(
    task_context: dict[str, Any] | None,
    *,
    prompt: str = "",
    capability: str = "",
    operation: str = "",
) -> dict[str, Any]:
    """Normalize loose task context into the scorer's expected shape."""
    context = dict(task_context or {})

    needs = context.get("needs") or []
    if isinstance(needs, str):
        needs = [needs]

    text_fragments: list[str] = []
    for key in ("intent", "style", "brief", "goal", "platform"):
        value = context.get(key)
        if isinstance(value, str) and value.strip():
            text_fragments.append(value.strip())
    text_fragments.extend(str(item).strip() for item in needs if str(item).strip())
    if prompt.strip():
        text_fragments.append(prompt.strip())

    combined_text = " ".join(text_fragments).strip()
    if not context.get("intent"):
        context["intent"] = combined_text

    style_keywords = {
        str(item).lower().strip()
        for item in (context.get("style_keywords") or [])
        if str(item).strip()
    }
    for source in [context.get("style"), context.get("platform"), *needs]:
        if isinstance(source, str):
            style_keywords.update(_tokenize_text(source))
    context["style_keywords"] = sorted(style_keywords)

    if not context.get("asset_type"):
        asset_type_map = {
            "video_generation": "video",
            "image_generation": "image",
            "tts": "voice",
            "music_generation": "music",
        }
        if capability in asset_type_map:
            context["asset_type"] = asset_type_map[capability]

    if "motion_required" not in context and capability == "video_generation":
        context["motion_required"] = True

    if "budget_remaining_usd" not in context and context.get("budget_usd") is not None:
        context["budget_remaining_usd"] = context["budget_usd"]

    text_tokens = set(_tokenize_text(combined_text))
    generated_visual_signal = bool(text_tokens & _GENERATED_VISUAL_TERMS)
    stock_visual_signal = bool(text_tokens & _STOCK_VISUAL_TERMS)
    if "prefers_generated_visuals" not in context:
        context["prefers_generated_visuals"] = (
            generated_visual_signal and not stock_visual_signal
        )
    if "wants_reference_conditioning" not in context:
        context["wants_reference_conditioning"] = (
            operation in {"image_to_video", "reference_to_video"}
            or bool(text_tokens & _REFERENCE_TERMS)
        )
    if "wants_image_editing" not in context:
        context["wants_image_editing"] = (
            operation == "edit" or bool(text_tokens & _IMAGE_EDIT_TERMS)
        )

    return context


def _is_stock_like_provider(info: dict[str, Any]) -> bool:
    provider = str(info.get("provider", "")).lower()
    if provider in {"pexels", "pixabay"}:
        return True

    words = set()
    for desc in info.get("best_for", []):
        words.update(_tokenize_text(str(desc)))
    return bool(words & {"stock", "footage", "b-roll", "library"})


def score_provider(tool, task_context: dict[str, Any]) -> ProviderScore:
    """Score a provider against a task context.

    Args:
        tool: A BaseTool instance.
        task_context: Dict with keys:
            - intent (str): What the asset is for
            - style_keywords (list[str]): Visual/audio style descriptors
            - budget_remaining_usd (float|None): Remaining budget
            - locked_providers (set[str]): Providers already chosen
            - motion_required (bool): Whether motion is a hard requirement
            - asset_type (str): "image", "video", "audio", "music", "voice"
    """
    task_context = normalize_task_context(task_context)
    info = safe_tool_info(tool)
    # .value on the ToolStatus enum returns "available" / "degraded" / "unavailable".
    # str() on the enum returns "ToolStatus.AVAILABLE", which never matches the
    # lowercase branches below — older code had every available tool scoring 0.0
    # on reliability.
    status = safe_tool_status(tool).value

    best_for = set(info.get("best_for", []))
    intent = task_context.get("intent", "")
    style_keywords = set(task_context.get("style_keywords", []))

    task_fit = _compute_task_fit(best_for, intent, style_keywords)

    # Reliability: uses historical success rate if available, else availability status.
    hist_success = info.get("historical_success_rate")  # 0.0-1.0 if tracked
    reliability: float | None = None
    if hist_success is not None:
        reliability = _score_value(hist_success, default=-1.0)
        if reliability < 0:
            reliability = None
    if reliability is None and status == "available":
        # Stable tools get higher baseline than experimental ones
        reliability = 0.95 if info.get("stability") == "production" else 0.8
    elif reliability is None and status == "degraded":
        reliability = 0.4
    elif reliability is None:
        reliability = 0.0

    # Control: from supports dict
    control = _compute_control(info.get("supports", {}))

    # Cost efficiency
    try:
        estimated_cost = tool.estimate_cost(task_context)
    except Exception:
        estimated_cost = 0.0
    estimated_cost = _finite_float(estimated_cost)
    if estimated_cost is None:
        estimated_cost = 0.0
    budget_remaining = _finite_float(task_context.get("budget_remaining_usd"))
    cost_efficiency = _compute_cost_efficiency(
        estimated_cost, budget_remaining
    )

    # Latency: uses measured p50 latency if available, else runtime class heuristic.
    measured_p50 = _finite_float(info.get("latency_p50_seconds"))  # historical median
    if measured_p50 is not None:
        # Map measured latency to a 0-1 score (sub-second is best, >60s is worst)
        if measured_p50 <= 1.0:
            latency = 1.0
        elif measured_p50 <= 10.0:
            latency = 0.8
        elif measured_p50 <= 30.0:
            latency = 0.6
        elif measured_p50 <= 60.0:
            latency = 0.4
        else:
            latency = 0.2
    else:
        runtime = info.get("runtime", "api")
        if runtime in ("local", "local_gpu"):
            latency = 0.9
        elif runtime == "hybrid":
            latency = 0.6
        else:
            latency = 0.4

    # Continuity
    continuity = _compute_continuity(
        info.get("provider", ""),
        set(task_context.get("locked_providers", [])),
    )

    # Output quality: uses measured quality score if available (e.g. from
    # user ratings or automated eval), else falls back to stability + tier.
    measured_quality = info.get("quality_score")  # 0.0-1.0 if tracked
    output_quality: float | None = None
    if measured_quality is not None:
        output_quality = _score_value(measured_quality, default=-1.0)
        if output_quality < 0:
            output_quality = None
    if output_quality is None:
        stability = info.get("stability", "experimental")
        tier = info.get("tier", "")
        quality_map = {"production": 0.9, "beta": 0.7, "experimental": 0.4}
        output_quality = quality_map.get(stability, 0.5)
        # Tier bonus: generate-tier tools that are production-stable get a nudge
        if tier == "generate" and stability == "production":
            output_quality = min(1.0, output_quality + 0.05)

    # Motion-required penalty: if task needs motion but tool is image-only
    if task_context.get("motion_required") and task_context.get("asset_type") == "video":
        cap = info.get("capability", "")
        if "video" not in cap:
            task_fit *= 0.2  # Heavy penalty

    supports = info.get("supports", {})
    stock_like = _is_stock_like_provider(info)
    asset_type = task_context.get("asset_type")

    if task_context.get("prefers_generated_visuals") and stock_like and asset_type in {"video", "image"}:
        task_fit *= 0.55
        output_quality *= 0.85

    if task_context.get("wants_reference_conditioning") and asset_type == "video":
        if (
            supports.get("image_to_video")
            or supports.get("reference_to_video")
            or supports.get("reference_image")
            or supports.get("multiple_reference_images")
        ):
            task_fit = min(1.0, task_fit + 0.18)
            control = min(1.0, control + 0.12)
        else:
            task_fit *= 0.7

    if task_context.get("wants_image_editing") and asset_type == "image":
        if supports.get("image_edit") or supports.get("style_transfer") or supports.get("multiple_reference_images"):
            task_fit = min(1.0, task_fit + 0.18)
            control = min(1.0, control + 0.10)
        else:
            task_fit *= 0.7

    # Premium-cinematic bonus: when a video task has cinematic/trailer intent,
    # reward providers that ship the premium feature set — native synchronized
    # audio, multi-shot single-generation, director-level camera control,
    # lip-sync from quoted dialogue. This is what makes Seedance 2.0 (and
    # peer premium APIs) meaningfully better than generic clip providers.
    if asset_type == "video":
        intent_words = _expand_synonyms(set(_tokenize_text(intent))) | set(style_keywords)
        cinematic_signal = bool(
            intent_words & {"cinematic", "film", "movie", "trailer", "teaser", "dramatic", "epic", "premium"}
        )
        if cinematic_signal:
            premium_features = [
                supports.get("native_audio"),
                supports.get("multi_shot"),
                supports.get("camera_direction"),
                supports.get("lip_sync"),
                supports.get("cinematic_quality"),
            ]
            matched = sum(1 for f in premium_features if f)
            if matched >= 3:
                task_fit = min(1.0, task_fit + 0.15)
                output_quality = min(1.0, output_quality + 0.10)
            elif matched >= 1:
                task_fit = min(1.0, task_fit + 0.05)

    return ProviderScore(
        tool_name=info.get("name", "unknown"),
        provider=info.get("provider", "unknown"),
        task_fit=min(1.0, task_fit),
        output_quality=output_quality,
        control=control,
        reliability=reliability,
        cost_efficiency=cost_efficiency,
        latency=latency,
        continuity=continuity,
    )


def rank_providers(
    tools: list,
    task_context: dict[str, Any],
) -> list[ProviderScore]:
    """Rank a list of tools by weighted score for a given task context.

    Returns scores sorted best-first.
    """
    scores = [score_provider(t, task_context) for t in tools]
    return sorted(scores, key=lambda s: s.weighted_score, reverse=True)


def format_ranking(rankings: list[ProviderScore], top_n: int = 5) -> str:
    """Format a ranking list for user presentation."""
    lines = []
    for i, r in enumerate(rankings[:top_n], 1):
        payload = r.to_dict()
        lines.append(
            f"  {i}. {r.tool_name} ({r.provider}) — "
            f"score: {payload['weighted_score']:.2f} "
            f"[fit={payload['task_fit']:.1f} quality={payload['output_quality']:.1f} "
            f"control={payload['control']:.1f} reliable={payload['reliability']:.1f} "
            f"cost={payload['cost_efficiency']:.1f}]"
        )
    return "\n".join(lines)
