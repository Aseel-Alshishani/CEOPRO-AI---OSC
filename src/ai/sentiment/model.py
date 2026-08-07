"""
CEOPRO AI - Multilingual Sentiment Classifier (spec S16).
Wraps a pretrained XLM-RoBERTa-based 3-class (positive/neutral/negative)
sentiment classifier - spec S16's stated model choice - covering Arabic,
English, and mixed content without any per-language routing. CPU-only (no
GPU yet); batched inference keeps a review backlog runnable on CPU.
"""

import os
from dataclasses import dataclass
from typing import List, Optional

import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

DEFAULT_MODEL_NAME = "cardiffnlp/twitter-xlm-roberta-base-sentiment"
MODEL_NAME = os.getenv("SENTIMENT_MODEL", DEFAULT_MODEL_NAME)
BATCH_SIZE = int(os.getenv("SENTIMENT_BATCH_SIZE", "16"))
MAX_TOKEN_LENGTH = int(os.getenv("SENTIMENT_MAX_TOKENS", "512"))

_tokenizer_cache = {}
_model_cache = {}


@dataclass
class SentimentPrediction:
    label: str
    positive_probability: float
    neutral_probability: float
    negative_probability: float
    confidence: float
    model_version: str

    def as_dict(self) -> dict:
        return {
            "label": self.label,
            "positive_probability": self.positive_probability,
            "neutral_probability": self.neutral_probability,
            "negative_probability": self.negative_probability,
            "confidence": self.confidence,
            "model_version": self.model_version,
        }


def _get_model_and_tokenizer(model_name: Optional[str] = None):
    """
    Lazily loads and caches the classifier - loading ~1GB of weights on every
    call would defeat batching entirely. Cached by name, mirroring
    src/ai/rag/embeddings.py's pattern, so tests can override SENTIMENT_MODEL
    without cross-contaminating a differently-configured caller.
    """
    model_name = model_name or MODEL_NAME
    if model_name not in _model_cache:
        _tokenizer_cache[model_name] = AutoTokenizer.from_pretrained(model_name)
        model = AutoModelForSequenceClassification.from_pretrained(model_name)
        model.eval()
        _model_cache[model_name] = model
    return _model_cache[model_name], _tokenizer_cache[model_name]


def _label_index_map(model) -> dict:
    """
    Maps the model's own id2label onto the DB schema's fixed vocabulary
    (positive/neutral/negative - sentiment_results.label's CHECK constraint)
    instead of assuming a fixed index order. Raises loudly instead of
    silently mislabeling if a differently-configured model doesn't use that
    vocabulary (e.g. generic LABEL_0/1/2 output).
    """
    normalized = {}
    for idx, raw_label in model.config.id2label.items():
        key = raw_label.strip().lower()
        if key not in ("positive", "neutral", "negative"):
            raise ValueError(
                f"Unrecognized sentiment label '{raw_label}' from model '{model.name_or_path}' - "
                f"expected positive/neutral/negative to match sentiment_results.label's CHECK constraint."
            )
        normalized[key] = idx
    missing = {"positive", "neutral", "negative"} - normalized.keys()
    if missing:
        raise ValueError(f"Model '{model.name_or_path}' is missing expected label(s): {missing}")
    return normalized


def classify(texts: List[str], model_name: Optional[str] = None) -> List[SentimentPrediction]:
    if not texts:
        return []

    model, tokenizer = _get_model_and_tokenizer(model_name)
    label_index = _label_index_map(model)
    resolved_model_name = model_name or MODEL_NAME

    predictions = []
    for start in range(0, len(texts), BATCH_SIZE):
        batch = texts[start:start + BATCH_SIZE]
        inputs = tokenizer(batch, return_tensors="pt", padding=True, truncation=True, max_length=MAX_TOKEN_LENGTH)
        with torch.no_grad():
            logits = model(**inputs).logits
        probs = torch.softmax(logits, dim=1)

        for row in probs:
            pos = float(row[label_index["positive"]])
            neu = float(row[label_index["neutral"]])
            neg = float(row[label_index["negative"]])
            scores = {"positive": pos, "neutral": neu, "negative": neg}
            top_label = max(scores, key=scores.get)
            predictions.append(
                SentimentPrediction(
                    label=top_label,
                    positive_probability=round(pos, 4),
                    neutral_probability=round(neu, 4),
                    negative_probability=round(neg, 4),
                    confidence=round(scores[top_label], 4),
                    model_version=resolved_model_name,
                )
            )
    return predictions
