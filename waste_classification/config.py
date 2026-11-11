"""
Central, validated configuration (``config/settings.json``).

Keeping every tunable value here (threshold, size limits, paths) means the
behaviour of the subsystem can be changed WITHOUT touching the code, which is
required by FR-07 (configurable threshold) and NFR-05 (maintainability).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Optional, Tuple, Union

from .exceptions import ConfigurationError

# Repository folder that contains ``config/``, ``models/`` ... (one level above the package)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SETTINGS_PATH = PROJECT_ROOT / "config" / "settings.json"

# The three disposal categories agreed by the whole team.
VALID_CATEGORIES: Tuple[str, ...] = ("recyclable", "compostable", "landfill")


@dataclass(frozen=True)
class Settings:
    """Immutable settings object. Invalid values raise ConfigurationError."""

    model_path: str = "models/waste_classifier"      # local folder or Hugging Face model id
    confidence_threshold: float = 0.60               # below this -> status "uncertain"
    max_file_size_mb: float = 5                      # upload size limit (NFR-07)
    min_resolution: int = 64                         # shortest image side in pixels (FR-02)
    allowed_formats: Tuple[str, ...] = ("JPEG", "PNG")
    top_k: int = 3                                   # number of ranked predictions (FR-06)
    class_mapping_file: str = "config/class_to_category.json"
    default_category: str = "landfill"               # used for classes missing in the mapping

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence_threshold <= 1.0:
            raise ConfigurationError("confidence_threshold must be between 0 and 1")
        if self.max_file_size_mb <= 0:
            raise ConfigurationError("max_file_size_mb must be > 0")
        if self.min_resolution < 1:
            raise ConfigurationError("min_resolution must be >= 1")
        if self.top_k < 1:
            raise ConfigurationError("top_k must be >= 1")
        if not self.allowed_formats:
            raise ConfigurationError("allowed_formats must not be empty")
        if self.default_category not in VALID_CATEGORIES:
            raise ConfigurationError(
                f"default_category must be one of {VALID_CATEGORIES}")

    # ------------------------------------------------------------------ #
    @classmethod
    def load(cls, path: Optional[Union[str, Path]] = None) -> "Settings":
        """Read settings from a JSON file (defaults to config/settings.json)."""
        path = Path(path) if path else DEFAULT_SETTINGS_PATH
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
        except FileNotFoundError as exc:
            raise ConfigurationError(f"Settings file not found: {path}") from exc
        except json.JSONDecodeError as exc:
            raise ConfigurationError(f"Settings file is not valid JSON: {exc}") from exc

        known = {f.name for f in fields(cls)}
        unknown = set(data) - known
        if unknown:
            raise ConfigurationError(f"Unknown settings keys: {sorted(unknown)}")
        if "allowed_formats" in data:
            data["allowed_formats"] = tuple(data["allowed_formats"])
        return cls(**data)

    def resolve(self, relative_path: str) -> Path:
        """Turn a path from the settings into an absolute path.

        Absolute paths are kept; relative ones are resolved against the project root.
        """
        p = Path(relative_path)
        return p if p.is_absolute() else PROJECT_ROOT / p
