"""Shared asset vocabulary used by cross-artifact validators."""

PRODUCT_VISIBLE_VALUES = frozenset(
    {"background", "partial", "hero", "detail", "packshot"}
)
VISUAL_ASSET_TYPES = frozenset({"image", "video", "animation"})
SOURCED_ASSET_SUBTYPES = frozenset(
    {
        "source",
        "sourced",
        "provided",
        "user_provided",
        "stock",
        "recorded",
        "library",
    }
)
SOURCED_ASSET_SOURCE_TOOLS = frozenset({"user_upload"})
