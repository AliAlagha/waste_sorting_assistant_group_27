"""
WasteClassifier - wraps a model *backend* and returns ranked predictions.

Design (NFR-05, maintainability)
--------------------------------
The classifier does not know HOW predictions are produced. It talks to an
``ImageClassifierBackend``. The default backend (Hugging Face model, see
model_loader.py) can be replaced by ONNX, a different network, or a fake
backend for tests - without changing the public input/output contract.

Pre-processing (FR-03: resize + normalise) is done inside the backend because
every pretrained model defines its own input size and normalisation values
(taken from the model's ``preprocessor_config.json``).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict, List

from PIL import Image

from .exceptions import ClassificationError, InferenceError
from .mapper import normalize_label
from .schemas import Prediction


class ImageClassifierBackend(ABC):
    """Interface every model implementation must follow."""

    #: Human-readable model version, copied into every result.
    version: str = "unknown"

    @abstractmethod
    def predict_scores(self, image: Image.Image) -> Dict[str, float]:
        """Return ``{class_label: probability}`` for ALL classes of the model."""

    def labels(self) -> List[str]:
        """All class names the model can output (optional; used for startup checks)."""
        return []


class WasteClassifier:
    """Produces the top-k predictions for a validated RGB image (FR-04, FR-06)."""

    def __init__(self, backend: ImageClassifierBackend) -> None:
        self.backend = backend

    @property
    def model_version(self) -> str:
        return self.backend.version

    def predict(self, image: Image.Image, k: int = 3) -> List[Prediction]:
        """Return up to ``k`` predictions sorted by confidence (highest first)."""
        try:
            scores = self.backend.predict_scores(image)
        except ClassificationError:
            raise                                   # already a well-defined error
        except Exception as exc:                    # any unexpected model failure
            raise InferenceError(f"Model inference failed: {exc}") from exc

        if not scores:
            raise InferenceError("Model returned no scores")

        ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[: max(1, k)]
        return [Prediction(item=normalize_label(label), confidence=round(float(p), 4))
                for label, p in ranked]
