"""Schema-valid demo artifacts for Backlot scripts.

These helpers intentionally live outside tests so README/demo scripts can run
from an installed or source checkout without depending on test modules.
"""

from __future__ import annotations


def minimal_research_brief(topic: str) -> dict:
    """Return a compact research_brief artifact that satisfies the schema."""
    return {
        "version": "1.0",
        "topic": topic,
        "research_date": "2026-03-27",
        "landscape": {
            "existing_content": [
                {
                    "title": "Existing Video 1",
                    "source": "youtube",
                    "angle": "tutorial",
                    "what_it_covers": "basics",
                },
                {
                    "title": "Existing Video 2",
                    "source": "blog",
                    "angle": "deep dive",
                    "what_it_covers": "advanced",
                },
                {
                    "title": "Existing Video 3",
                    "source": "youtube",
                    "angle": "comparison",
                    "what_it_covers": "alternatives",
                },
            ],
            "saturated_angles": ["basic tutorial"],
            "underserved_gaps": ["misconceptions about the topic"],
        },
        "data_points": [
            {
                "claim": "73% of viewers prefer a clear story arc",
                "source_url": "https://example.com/study",
                "credibility": "primary_source",
            },
            {
                "claim": "Short-form educational videos benefit from strong hooks",
                "source_url": "https://example.com/report",
                "credibility": "secondary_source",
            },
            {
                "claim": "Visual continuity improves viewer comprehension",
                "source_url": "https://example.com/survey",
                "credibility": "primary_source",
            },
        ],
        "audience_insights": {
            "common_questions": [
                "What is the story?",
                "Why does it matter?",
                "What should I remember?",
            ],
            "misconceptions": [
                {
                    "myth": "A cinematic demo needs real provider calls",
                    "reality": "A staged local demo can use deterministic placeholder media",
                }
            ],
            "knowledge_level": "Beginner to intermediate",
        },
        "angles_discovered": [
            {
                "name": "The Surprising Truth",
                "hook": "The simplest image can still carry a story.",
                "type": "contrarian",
                "why_now": "Local demos need zero-key proof paths",
                "grounded_in": ["data_point_1"],
            },
            {
                "name": "From Script To Board",
                "hook": "Watch the production board fill itself in.",
                "type": "evergreen",
                "why_now": "Transparent production state reduces uncertainty",
                "grounded_in": ["audience_q1"],
            },
            {
                "name": "Why Gates Matter",
                "hook": "Approval before render avoids expensive late fixes.",
                "type": "data_driven",
                "why_now": "Human review is central to governed AI video",
                "grounded_in": ["audience_q2"],
            },
        ],
        "sources": [
            {"url": "https://example.com/study", "title": "Story Arc Study", "used_for": "data_points"},
            {"url": "https://example.com/report", "title": "Hook Report", "used_for": "data_points"},
            {"url": "https://example.com/survey", "title": "Continuity Survey", "used_for": "data_points"},
            {"url": "https://example.com/forum", "title": "Audience Questions", "used_for": "audience_insights"},
            {"url": "https://example.com/blog", "title": "Content Landscape", "used_for": "landscape"},
        ],
    }
