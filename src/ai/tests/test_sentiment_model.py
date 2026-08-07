"""
Offline tests for the label-mapping/batching logic in src/ai/sentiment/model.py,
using a mocked transformer instead of the real ~1GB model - the real model is
covered separately (opt-in, downloads a real model) in
test_sentiment_model_real.py.
"""

from unittest.mock import MagicMock, patch

import torch

from src.ai.sentiment import model as sentiment_model


class _FakeConfig:
    def __init__(self, id2label):
        self.id2label = id2label


def _fake_model(id2label):
    fake = MagicMock()
    fake.config = _FakeConfig(id2label)
    fake.name_or_path = "fake-model"
    return fake


def test_label_index_map_normalizes_case_and_reads_order_from_model():
    fake = _fake_model({0: "Negative", 1: "Neutral", 2: "Positive"})
    mapping = sentiment_model._label_index_map(fake)
    assert mapping == {"negative": 0, "neutral": 1, "positive": 2}


def test_label_index_map_rejects_unrecognized_labels():
    fake = _fake_model({0: "LABEL_0", 1: "LABEL_1", 2: "LABEL_2"})
    try:
        sentiment_model._label_index_map(fake)
        assert False, "expected ValueError for non-sentiment label vocabulary"
    except ValueError as exc:
        assert "LABEL_0" in str(exc)


def test_label_index_map_rejects_model_missing_a_label():
    fake = _fake_model({0: "positive", 1: "negative"})
    try:
        sentiment_model._label_index_map(fake)
        assert False, "expected ValueError for missing 'neutral' label"
    except ValueError as exc:
        assert "neutral" in str(exc)


def test_classify_returns_empty_list_for_no_texts():
    assert sentiment_model.classify([]) == []


def test_classify_maps_scores_correctly_even_with_non_canonical_label_order():
    # Positive lives at index 0 here, not the cardiffnlp model's actual order -
    # proves classify() doesn't assume any fixed index -> label mapping
    # (the project has been bitten by exactly this kind of ordering
    # assumption before, in the NER regex alternation-order bug).
    id2label = {0: "positive", 1: "negative", 2: "neutral"}
    fake_model = _fake_model(id2label)
    fake_model.return_value = MagicMock(logits=torch.tensor([[5.0, 0.0, 0.0]]))
    fake_tokenizer = MagicMock(return_value={"input_ids": torch.zeros((1, 3), dtype=torch.long)})

    with patch.object(sentiment_model, "_get_model_and_tokenizer", return_value=(fake_model, fake_tokenizer)):
        predictions = sentiment_model.classify(["great product"], model_name="fake-model")

    assert len(predictions) == 1
    prediction = predictions[0]
    assert prediction.label == "positive"
    assert prediction.model_version == "fake-model"
    assert prediction.positive_probability > prediction.negative_probability
    assert prediction.positive_probability > prediction.neutral_probability
    # Each probability is independently rounded to 4dp in model.py, so their
    # sum can drift slightly from 1.0 - allow for that rounding, not exactness.
    total = prediction.positive_probability + prediction.neutral_probability + prediction.negative_probability
    assert abs(total - 1.0) < 1e-3


def test_classify_splits_into_batches_of_batch_size(monkeypatch):
    monkeypatch.setattr(sentiment_model, "BATCH_SIZE", 2)
    id2label = {0: "positive", 1: "neutral", 2: "negative"}
    fake_model = _fake_model(id2label)
    fake_model.side_effect = lambda **kwargs: MagicMock(logits=torch.zeros((kwargs["input_ids"].shape[0], 3)))
    fake_tokenizer = MagicMock(side_effect=lambda batch, **kw: {"input_ids": torch.zeros((len(batch), 3), dtype=torch.long)})

    with patch.object(sentiment_model, "_get_model_and_tokenizer", return_value=(fake_model, fake_tokenizer)):
        predictions = sentiment_model.classify(["a", "b", "c"], model_name="fake-model")

    assert len(predictions) == 3
    assert fake_tokenizer.call_count == 2  # batches of [2, 1]
    assert fake_model.call_count == 2
