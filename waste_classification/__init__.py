"""
AI Waste Classification subsystem.

Public API::

    from waste_classification import ClassificationService
    service = ClassificationService.from_settings()
    result = service.classify(open("bottle.jpg", "rb").read())
    print(result.to_dict())
"""
from .classifier import ImageClassifierBackend, WasteClassifier
from .config import Settings
from .exceptions import (
    ClassificationError,
    ConfigurationError,
    CorruptedImageError,
    FileTooLargeError,
    ImageTooSmallError,
    InferenceError,
    InvalidImageError,
    ModelLoadError,
    UnsupportedFormatError,
)
from .mapper import CategoryMapper, normalize_label
from .model_loader import ModelLoader
from .schemas import ClassificationResult, Prediction
from .service import ClassificationService
from .validator import ImageValidator

__all__ = [
    "CategoryMapper", "ClassificationError", "ClassificationResult", "ClassificationService",
    "ConfigurationError", "CorruptedImageError", "FileTooLargeError", "ImageClassifierBackend",
    "ImageTooSmallError", "ImageValidator", "InferenceError", "InvalidImageError",
    "ModelLoadError", "ModelLoader", "Prediction", "Settings", "UnsupportedFormatError",
    "WasteClassifier", "normalize_label",
]
__version__ = "1.0.0"
