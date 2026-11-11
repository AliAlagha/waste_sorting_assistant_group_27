"""
ModelLoader + HuggingFaceBackend.

ModelLoader.load() accepts either
  * a LOCAL folder produced by ``scripts/train.py`` (recommended), or
  * a Hugging Face model id such as "your-user/waste-classifier" (downloaded on first use).

``torch`` and ``transformers`` are imported lazily, inside the functions, so the rest of
the package (validator, mapper, service, unit tests with a fake backend) works even if
those heavy libraries are not installed.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, Union

from PIL import Image

from .classifier import ImageClassifierBackend
from .exceptions import ModelLoadError

logger = logging.getLogger(__name__)

#: File written by scripts/train.py next to the model weights.
METADATA_FILE = "model_metadata.json"


class HuggingFaceBackend(ImageClassifierBackend):
    """Image-classification model + processor from the Hugging Face ``transformers`` library."""

    def __init__(self, processor, model, torch_module, device: str, version: str) -> None:
        self._processor = processor      # resize + normalise (FR-03)
        self._model = model
        self._torch = torch_module
        self._device = device
        self.version = version

    def labels(self):
        return list(self._model.config.id2label.values())

    def predict_scores(self, image: Image.Image) -> Dict[str, float]:
        torch = self._torch
        # 1) pre-process: resize + normalise according to the model's config
        inputs = self._processor(images=image, return_tensors="pt")
        inputs = {k: v.to(self._device) for k, v in inputs.items()}
        # 2) forward pass without gradient tracking (faster, less memory)
        with torch.inference_mode():
            logits = self._model(**inputs).logits
        # 3) logits -> probabilities that sum to 1
        probs = torch.softmax(logits, dim=-1)[0].tolist()
        id2label = self._model.config.id2label
        return {id2label[i]: p for i, p in enumerate(probs)}


class ModelLoader:
    """Loads a trained model once and returns a ready-to-use backend."""

    def __init__(self, model_path: Union[str, Path]) -> None:
        self.model_path = str(model_path)

    def load(self) -> HuggingFaceBackend:
        try:
            import torch
            from transformers import AutoImageProcessor, AutoModelForImageClassification
        except ImportError as exc:
            raise ModelLoadError(
                "torch and transformers are required: pip install -r requirements.txt") from exc

        try:
            processor = AutoImageProcessor.from_pretrained(self.model_path)
            model = AutoModelForImageClassification.from_pretrained(self.model_path)
        except Exception as exc:
            raise ModelLoadError(
                f"Could not load model from '{self.model_path}'. Did you train it "
                f"(scripts/train.py) or download it into models/? Details: {exc}") from exc

        device = "cuda" if torch.cuda.is_available() else "cpu"
        model.to(device)
        model.eval()                      # inference mode (disables dropout)
        version = self._read_version()
        logger.info("Loaded model '%s' (version %s) on %s", self.model_path, version, device)
        return HuggingFaceBackend(processor, model, torch, device, version)

    def _read_version(self) -> str:
        """Version string from model_metadata.json, or the folder name as a fallback."""
        meta = Path(self.model_path) / METADATA_FILE
        if meta.is_file():
            try:
                return json.loads(meta.read_text(encoding="utf-8")).get(
                    "model_version", Path(self.model_path).name)
            except (OSError, json.JSONDecodeError):
                logger.warning("Could not read %s", meta)
        return Path(self.model_path).name
