from __future__ import annotations

import json

import numpy as np

from lib.corpus import EMBED_DIM, ClipRecord, Corpus


def _record(clip_id: str) -> ClipRecord:
    return ClipRecord(
        clip_id=clip_id,
        source="test",
        source_id=clip_id,
        source_url=f"https://example.test/{clip_id}",
        local_path=f"clips/{clip_id}.mp4",
    )


def _vector(first_value: float = 1.0) -> np.ndarray:
    vector = np.zeros(EMBED_DIM, dtype=np.float32)
    vector[0] = first_value
    return vector


def test_corpus_load_maps_clip_ids_to_record_rows_when_index_contains_blank_lines(
    tmp_path,
):
    corpus_dir = tmp_path / "corpus"
    corpus_dir.mkdir()
    rows = [_record("clip_a"), _record("clip_b")]
    with open(corpus_dir / "index.jsonl", "w", encoding="utf-8") as f:
        f.write(json.dumps(rows[0].__dict__) + "\n")
        f.write("\n")
        f.write(json.dumps(rows[1].__dict__) + "\n")
    np.save(corpus_dir / "embeddings.npy", np.zeros((2, EMBED_DIM), dtype=np.float32))
    np.save(corpus_dir / "tag_embeddings.npy", np.zeros((2, EMBED_DIM), dtype=np.float32))

    corpus = Corpus(corpus_dir)
    corpus.load()

    assert corpus.get("clip_a").clip_id == "clip_a"
    assert corpus.get("clip_b").clip_id == "clip_b"


def test_corpus_load_normalizes_single_vector_embedding_banks(tmp_path):
    corpus_dir = tmp_path / "corpus"
    corpus_dir.mkdir()
    row = _record("clip_a")
    with open(corpus_dir / "index.jsonl", "w", encoding="utf-8") as f:
        f.write(json.dumps(row.__dict__) + "\n")
    vector = _vector()
    np.save(corpus_dir / "embeddings.npy", vector)
    np.save(corpus_dir / "tag_embeddings.npy", vector)

    corpus = Corpus(corpus_dir)
    corpus.load()

    assert corpus.clip_embeddings.shape == (1, EMBED_DIM)
    assert corpus.tag_embeddings.shape == (1, EMBED_DIM)
    results = corpus.rank_by_text(vector, k=1)
    assert [(record.clip_id, score) for record, score in results] == [("clip_a", 1.0)]


def test_corpus_load_preserves_rows_when_tag_embedding_bank_is_missing(tmp_path):
    corpus_dir = tmp_path / "corpus"
    corpus_dir.mkdir()
    rows = [_record("clip_a"), _record("clip_b")]
    with open(corpus_dir / "index.jsonl", "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row.__dict__) + "\n")
    clip_vectors = np.zeros((2, EMBED_DIM), dtype=np.float32)
    clip_vectors[0, 0] = 1.0
    clip_vectors[1, 1] = 1.0
    np.save(corpus_dir / "embeddings.npy", clip_vectors)

    corpus = Corpus(corpus_dir)
    corpus.load()

    assert [record.clip_id for record in corpus.records] == ["clip_a", "clip_b"]
    assert corpus.clip_embeddings.shape == (2, EMBED_DIM)
    assert corpus.tag_embeddings.shape == (2, EMBED_DIM)
    assert np.all(corpus.tag_embeddings == 0.0)
    results = corpus.rank_by_text(clip_vectors[0], k=1)
    assert [record.clip_id for record, _score in results] == ["clip_a"]
    assert np.isclose(results[0][1], 0.7)


def test_corpus_load_treats_corrupt_embedding_files_as_empty_banks(tmp_path):
    corpus_dir = tmp_path / "corpus"
    corpus_dir.mkdir()
    row = _record("clip_a")
    with open(corpus_dir / "index.jsonl", "w", encoding="utf-8") as f:
        f.write(json.dumps(row.__dict__) + "\n")
    (corpus_dir / "embeddings.npy").write_bytes(b"not a numpy file")
    (corpus_dir / "tag_embeddings.npy").write_bytes(b"not a numpy file")

    corpus = Corpus(corpus_dir)
    corpus.load()

    assert len(corpus) == 0
    assert corpus.clip_embeddings.shape == (0, EMBED_DIM)
    assert corpus.tag_embeddings.shape == (0, EMBED_DIM)


def test_corpus_save_failure_preserves_previous_persisted_embedding_banks(
    tmp_path, monkeypatch
):
    corpus_dir = tmp_path / "corpus"
    corpus = Corpus(corpus_dir)
    corpus.add(_record("clip_a"), _vector(), _vector())
    corpus.save()

    corpus.add(_record("clip_b"), _vector(0.5), _vector(0.5))

    def corrupting_save(path, arr):
        path.write_bytes(b"partial numpy output")
        raise OSError("simulated interrupted save")

    monkeypatch.setattr("lib.corpus.np.save", corrupting_save)

    try:
        corpus.save()
    except OSError:
        pass

    reloaded = Corpus(corpus_dir)
    reloaded.load()
    assert [record.clip_id for record in reloaded.records] == ["clip_a"]
    assert reloaded.clip_embeddings.shape == (1, EMBED_DIM)
    assert reloaded.tag_embeddings.shape == (1, EMBED_DIM)


def test_corpus_diversify_drops_duplicate_candidate_ids(tmp_path):
    corpus = Corpus(tmp_path / "corpus")
    vec_a = _vector()
    vec_b = np.zeros(EMBED_DIM, dtype=np.float32)
    vec_b[1] = 1.0
    corpus.add(_record("clip_a"), vec_a, vec_a)
    corpus.add(_record("clip_b"), vec_b, vec_b)

    kept = corpus.diversify(["clip_a", "clip_a", "clip_b"], n=2)

    assert kept == ["clip_a", "clip_b"]


def test_corpus_diversify_respects_zero_requested_count(tmp_path):
    corpus = Corpus(tmp_path / "corpus")
    corpus.add(_record("clip_a"), _vector(), _vector())

    assert corpus.diversify(["clip_a"], n=0) == []
