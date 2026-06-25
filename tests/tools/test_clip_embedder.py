from __future__ import annotations

import builtins

import pytest

import lib.clip_embedder as clip_embedder


class _FakeImage:
    def __init__(self):
        self.closed = False

    def convert(self, mode):
        assert mode == "RGB"
        return self

    def close(self):
        self.closed = True


def test_embed_images_closes_opened_images_when_processor_fails(monkeypatch, tmp_path):
    opened: list[_FakeImage] = []
    real_import = builtins.__import__

    class FailingProcessor:
        def __call__(self, **kwargs):
            raise RuntimeError("processor failed")

    def fake_open(path):
        image = _FakeImage()
        opened.append(image)
        return image

    def fail_on_torch_import(name, *args, **kwargs):
        if name == "torch":
            raise AssertionError("torch should not be imported when CLIP is already loaded")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(clip_embedder, "_load", lambda: None)
    monkeypatch.setattr(clip_embedder, "_MODEL", object())
    monkeypatch.setattr(clip_embedder, "_PROCESSOR", FailingProcessor())
    monkeypatch.setattr(clip_embedder, "_DEVICE", "cpu")
    monkeypatch.setattr(builtins, "__import__", fail_on_torch_import)
    monkeypatch.setattr("PIL.Image.open", fake_open)

    with pytest.raises(RuntimeError, match="processor failed"):
        clip_embedder.embed_images([tmp_path / "frame.jpg"])

    assert opened
    assert all(image.closed for image in opened)
