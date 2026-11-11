"""
Data structures exchanged with the other subsystems.

``ClassificationResult.to_dict()`` is THE contract of this subsystem
(NFR-09). Example of a successful response::

    {
      "status": "ok",                    # "ok" | "uncertain" | "error"
      "item": "plastic",                 # predicted waste-item class
      "category": "recyclable",          # recyclable | compostable | landfill
      "confidence": 0.92,                # 0..1
      "top3": [{"item": "plastic", "confidence": 0.92}, ...],
      "message": null,                   # human-readable hint (uncertain / error)
      "error_code": null,                # machine-readable code when status == "error"
      "model_version": "mobilenet_v2-2026-11-09",
      "processing_ms": 183.4,
      "timestamp": "2026-11-09T10:15:30+00:00"
    }

If you change a field name or meaning, bump the version in README.md and tell
the Backend / Frontend / Recommendation owners.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# Possible values of ClassificationResult.status
STATUS_OK = "ok"                # confident prediction
STATUS_UNCERTAIN = "uncertain"  # prediction below threshold -> ask the user to verify
STATUS_ERROR = "error"          # nothing could be predicted (see error_code)


def _utc_now() -> str:
    """Current UTC time as an ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class Prediction:
    """One ranked model output: a class name and its probability."""

    item: str
    confidence: float


@dataclass
class ClassificationResult:
    """Structured answer of the classification subsystem."""

    status: str
    item: Optional[str] = None
    category: Optional[str] = None
    confidence: Optional[float] = None
    top_predictions: List[Prediction] = field(default_factory=list)
    message: Optional[str] = None
    error_code: Optional[str] = None
    model_version: Optional[str] = None
    processing_ms: Optional[float] = None
    timestamp: str = field(default_factory=_utc_now)

    # ------------------------------------------------------------------ #
    @classmethod
    def error(cls, code: str, message: str, **extra: Any) -> "ClassificationResult":
        """Shortcut for building an error result (FR-08)."""
        return cls(status=STATUS_ERROR, error_code=code, message=message, **extra)

    @property
    def is_error(self) -> bool:
        return self.status == STATUS_ERROR

    def to_dict(self) -> Dict[str, Any]:
        """JSON-serialisable dictionary following the shared contract."""
        return {
            "status": self.status,
            "item": self.item,
            "category": self.category,
            "confidence": self.confidence,
            "top3": [{"item": p.item, "confidence": p.confidence}
                     for p in self.top_predictions],
            "message": self.message,
            "error_code": self.error_code,
            "model_version": self.model_version,
            "processing_ms": self.processing_ms,
            "timestamp": self.timestamp,
        }
