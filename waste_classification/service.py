"""
ClassificationService - the ONE entry point other subsystems use.

    service = ClassificationService.from_settings()
    result  = service.classify(image_bytes)      # never raises
    payload = result.to_dict()                   # JSON contract (see schemas.py)

Pipeline (each step maps to a requirement):
    bytes -> ImageValidator (FR-01/02) -> WasteClassifier (FR-03/04/05/06)
          -> ConfidenceCheck (FR-07)   -> CategoryMapper -> ClassificationResult
Errors at any step are converted to a structured result (FR-08, NFR-04): the
caller never has to wrap this method in try/except.
"""
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Optional, Union

from .classifier import WasteClassifier
from .config import Settings
from .exceptions import ClassificationError
from .mapper import CategoryMapper
from .model_loader import ModelLoader
from .schemas import (
    STATUS_OK,
    STATUS_UNCERTAIN,
    ClassificationResult,
)
from .validator import ImageValidator

logger = logging.getLogger(__name__)

UNCERTAIN_MESSAGE = "Not sure about this item. Please verify the result or retake the photo."


class ClassificationService:
    """Coordinates validation, inference, confidence check and category mapping."""

    def __init__(
        self,
        validator: ImageValidator,
        classifier: WasteClassifier,
        mapper: CategoryMapper,
        confidence_threshold: float = 0.60,
        top_k: int = 3,
    ) -> None:
        self.validator = validator
        self.classifier = classifier
        self.mapper = mapper
        self.confidence_threshold = confidence_threshold
        self.top_k = top_k

    # ------------------------------------------------------------------ #
    # Construction helper
    # ------------------------------------------------------------------ #
    @classmethod
    def from_settings(cls, settings: Optional[Settings] = None) -> "ClassificationService":
        """Build a fully wired service from config/settings.json."""
        settings = settings or Settings.load()
        validator = ImageValidator(
            settings.max_file_size_mb, settings.min_resolution, settings.allowed_formats)
        mapper = CategoryMapper.from_json(
            settings.resolve(settings.class_mapping_file), settings.default_category)
        backend = ModelLoader(settings.resolve(settings.model_path)).load()

        # Startup sanity check: every class the model can output should be mapped.
        missing = mapper.unmapped(backend.labels())
        if missing:
            logger.warning("Classes without category mapping (will use '%s'): %s",
                           settings.default_category, missing)

        return cls(validator, WasteClassifier(backend), mapper,
                   settings.confidence_threshold, settings.top_k)

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def classify(self, data: bytes) -> ClassificationResult:
        """Classify an image given as raw bytes. Never raises."""
        started = time.perf_counter()
        version = self.classifier.model_version
        try:
            result = self._run_pipeline(data)
        except ClassificationError as exc:
            logger.info("Classification failed: %s (%s)", exc.message, exc.code)
            result = ClassificationResult.error(exc.code, exc.message)
        except Exception as exc:  # last line of defence (NFR-04: never crash)
            logger.exception("Unexpected error during classification")
            result = ClassificationResult.error("INTERNAL_ERROR", f"Unexpected error: {exc}")

        result.model_version = version
        result.processing_ms = round((time.perf_counter() - started) * 1000, 1)
        return result

    def classify_file(self, path: Union[str, Path]) -> ClassificationResult:
        """Convenience wrapper: read an image file from disk and classify it."""
        try:
            data = Path(path).read_bytes()
        except OSError as exc:
            return ClassificationResult.error("FILE_NOT_FOUND", f"Cannot read file: {exc}")
        return self.classify(data)

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #
    def _run_pipeline(self, data: bytes) -> ClassificationResult:
        image = self.validator.validate(data)                       # may raise InvalidImageError
        predictions = self.classifier.predict(image, k=self.top_k)  # may raise InferenceError

        best = predictions[0]
        confident = best.confidence >= self.confidence_threshold    # FR-07
        return ClassificationResult(
            status=STATUS_OK if confident else STATUS_UNCERTAIN,
            item=best.item,
            category=self.mapper.to_category(best.item),
            confidence=best.confidence,
            top_predictions=predictions,
            message=None if confident else UNCERTAIN_MESSAGE,
        )
