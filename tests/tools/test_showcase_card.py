from __future__ import annotations

from tools.video.showcase_card import ShowcaseCard


def test_showcase_card_idempotency_key_includes_output_and_render_parameters():
    tool = ShowcaseCard()
    base = {
        "input_path": "clip.mp4",
        "output_path": "out-a.mp4",
        "title": "Demo",
        "subtitle": "Short description",
        "output_width": 1080,
        "output_height": 1920,
        "background_color": "0x0A0F1A",
        "title_font": "segoeuib.ttf",
        "title_font_size": 52,
        "subtitle_font_size": 28,
        "title_color": "white",
        "watermark": "Brand",
    }
    variants = [
        {"output_path": "out-b.mp4"},
        {"output_width": 720},
        {"output_height": 1280},
        {"background_color": "0xFFFFFF"},
        {"title_font": "arial.ttf"},
        {"title_font_size": 60},
        {"subtitle_font_size": 32},
        {"title_color": "yellow"},
        {"watermark": "Other"},
    ]

    base_key = tool.idempotency_key(base)

    for variant in variants:
        assert tool.idempotency_key({**base, **variant}) != base_key
