import pytest

from src.ai.rag.chunking import chunk_text


def test_empty_text_returns_no_chunks():
    assert chunk_text("") == []
    assert chunk_text("   ") == []


def test_short_text_returns_single_chunk():
    chunks = chunk_text("hello world", chunk_size_words=200, overlap_words=40)
    assert chunks == ["hello world"]


def test_long_text_splits_into_multiple_overlapping_chunks():
    words = [f"word{i}" for i in range(500)]
    text = " ".join(words)
    overlap_words = 40
    chunks = chunk_text(text, chunk_size_words=200, overlap_words=overlap_words)

    assert len(chunks) > 1
    # last word of chunk 0 must reappear at the start of chunk 1 - that's the overlap
    first_chunk_words = chunks[0].split()
    second_chunk_words = chunks[1].split()
    assert first_chunk_words[-1] in second_chunk_words[:overlap_words]


def test_no_words_are_dropped_across_chunk_boundaries():
    words = [f"w{i}" for i in range(50)]
    text = " ".join(words)
    chunks = chunk_text(text, chunk_size_words=20, overlap_words=5)

    seen = set()
    for chunk in chunks:
        seen.update(chunk.split())
    assert seen == set(words)


def test_arabic_text_is_chunked_by_word_boundaries():
    arabic_text = " ".join(["كلمة"] * 30)
    chunks = chunk_text(arabic_text, chunk_size_words=10, overlap_words=2)
    assert len(chunks) > 1
    assert all(c.strip() for c in chunks)


def test_invalid_chunk_size_raises():
    with pytest.raises(ValueError):
        chunk_text("some text", chunk_size_words=0)


def test_overlap_greater_than_chunk_size_raises():
    with pytest.raises(ValueError):
        chunk_text("some text", chunk_size_words=10, overlap_words=10)
