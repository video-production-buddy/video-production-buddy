"""Retrieve curated professional advertising knowledge for ad-video planning."""

from __future__ import annotations

import time
from typing import Any

from lib.ad_knowledge import retrieve_ad_knowledge
from tools.base_tool import (
    BaseTool,
    Determinism,
    ExecutionMode,
    ResourceProfile,
    ToolResult,
    ToolRuntime,
    ToolStability,
    ToolTier,
)


class AdKnowledgeRetriever(BaseTool):
    name = "ad_knowledge_retriever"
    version = "0.1.0"
    tier = ToolTier.ANALYZE
    capability = "knowledge_retrieval"
    provider = "video_production_buddy"
    stability = ToolStability.BETA
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.DETERMINISTIC
    runtime = ToolRuntime.LOCAL

    dependencies: list[str] = []
    install_instructions = "No setup required. Uses Video Production Buddy curated knowledge cards."
    agent_skills: list[str] = []

    capabilities = [
        "ad_producer_knowledge_retrieval",
        "bm25_knowledge_search",
        "embedding_backend_fallback",
        "auditable_knowledge_refs",
    ]
    supports = {
        "default_backend": "bm25",
        "embedding_backend_interface": True,
        "network_required": False,
        "auditable_source_refs": True,
    }
    best_for = [
        "grounding ad-video intelligence in professional producer doctrine",
        "retrieving stable hook, proof, rhythm, visual, and compliance guidance",
    ]
    not_good_for = [
        "discovering current platform trends",
        "analyzing a concrete viral video reference",
    ]
    input_schema = {
        "type": "object",
        "properties": {
            "product_category": {"type": "string"},
            "platform": {"type": "string"},
            "audience": {"type": "string"},
            "objectives": {"type": "array", "items": {"type": "string"}},
            "validation_targets": {"type": "array", "items": {"type": "string"}},
            "backend": {
                "type": "string",
                "enum": ["auto", "bm25", "embedding", "hybrid"],
                "default": "auto",
            },
            "top_k": {"type": "integer", "minimum": 1, "maximum": 20, "default": 6},
        },
    }
    output_schema = {
        "type": "object",
        "required": [
            "retrieval_backend",
            "cards_used",
            "application_recommendations",
            "contraindications",
            "gaps",
            "warnings",
        ],
        "additionalProperties": False,
        "properties": {
            "retrieval_backend": {"type": "string", "enum": ["bm25", "embedding", "hybrid"]},
            "cards_used": {"type": "array"},
            "application_recommendations": {"type": "array"},
            "contraindications": {"type": "array"},
            "gaps": {"type": "array"},
            "warnings": {"type": "array"},
        },
    }
    resource_profile = ResourceProfile(cpu_cores=1, ram_mb=128, disk_mb=1, network_required=False)
    user_visible_verification = [
        "Inspect cards_used[].source_ref values and thread selected refs into script/scene_plan",
    ]

    def estimate_cost(self, inputs: dict[str, Any]) -> float:
        return 0.0

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        started = time.time()
        try:
            data = retrieve_ad_knowledge(inputs)
            return ToolResult(
                success=True,
                data=data,
                cost_usd=0.0,
                duration_seconds=time.time() - started,
            )
        except Exception as exc:
            return ToolResult(
                success=False,
                error=str(exc),
                duration_seconds=time.time() - started,
            )
