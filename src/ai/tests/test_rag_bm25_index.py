from src.ai.rag.bm25_index import BM25Index, tokenize


def test_tokenize_lowercases_and_splits_on_word_boundaries():
    assert tokenize("Hello, World! Prices: $18.00") == ["hello", "world", "prices", "18", "00"]


def test_tokenize_handles_arabic_text():
    tokens = tokenize("مرحبا بكم في المتجر")
    assert tokens == ["مرحبا", "بكم", "في", "المتجر"]


def test_empty_index_returns_no_results():
    index = BM25Index([])
    assert len(index) == 0
    assert index.query("anything") == []


def test_query_ranks_most_relevant_chunk_first():
    chunks = [
        ("c1", "Sunscreen SPF 50 is our best selling summer product"),
        ("c2", "Moisturizer lotion for dry winter skin"),
        ("c3", "Sunscreen and sun protection are essential in summer"),
    ]
    index = BM25Index(chunks)
    results = index.query("sunscreen summer protection", top_k=3)

    assert len(results) > 0
    assert results[0].chunk_id in ("c1", "c3")  # both mention sunscreen/summer, unlike c2
    assert all(r.score >= 0 for r in results)


def test_query_with_no_lexical_overlap_returns_no_results():
    chunks = [("c1", "Sunscreen SPF 50 summer product")]
    index = BM25Index(chunks)
    results = index.query("completely unrelated automotive machinery parts")
    assert results == []


def test_top_k_limits_result_count():
    chunks = [(f"c{i}", "sunscreen summer product line item") for i in range(10)]
    index = BM25Index(chunks)
    results = index.query("sunscreen summer", top_k=3)
    assert len(results) <= 3


def test_len_reflects_chunk_count():
    chunks = [("c1", "text one"), ("c2", "text two")]
    assert len(BM25Index(chunks)) == 2
