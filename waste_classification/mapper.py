"""
CategoryMapper - converts a waste *item class* (e.g. "brown-glass") into a
disposal *category* (recyclable / compostable / landfill).

The mapping lives in ``config/class_to_category.json`` so it can be edited
without code changes. The final category rules must be aligned with the
Recycling Recommendation subsystem.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Iterable, List, Union

from .config import VALID_CATEGORIES
from .exceptions import ConfigurationError


def normalize_label(label: str) -> str:
    """Canonical form of a class name: lower-case, words joined by '-'.

    "Brown_Glass", "brown glass" and "BROWN-GLASS" all become "brown-glass".
    Used for model labels AND mapping keys so that they always match.
    """
    return label.strip().lower().replace("_", "-").replace(" ", "-")


class CategoryMapper:
    """Looks up the disposal category of a predicted class."""

    def __init__(self, mapping: Dict[str, str], default_category: str = "landfill") -> None:
        if default_category not in VALID_CATEGORIES:
            raise ConfigurationError(f"default_category must be one of {VALID_CATEGORIES}")
        # Drop documentation keys such as "_comment" and normalise the rest.
        cleaned = {normalize_label(k): v for k, v in mapping.items()
                   if not k.startswith("_")}
        bad = {k: v for k, v in cleaned.items() if v not in VALID_CATEGORIES}
        if bad:
            raise ConfigurationError(
                f"Invalid categories in mapping {bad}; allowed: {VALID_CATEGORIES}")
        self.mapping = cleaned
        self.default_category = default_category

    @classmethod
    def from_json(cls, path: Union[str, Path], default_category: str = "landfill") -> "CategoryMapper":
        """Build a mapper from a JSON file."""
        try:
            with open(path, encoding="utf-8") as fh:
                return cls(json.load(fh), default_category)
        except FileNotFoundError as exc:
            raise ConfigurationError(f"Mapping file not found: {path}") from exc
        except json.JSONDecodeError as exc:
            raise ConfigurationError(f"Mapping file is not valid JSON: {exc}") from exc

    def to_category(self, item: str) -> str:
        """Category of ``item``; unknown classes fall back to the default (safe choice)."""
        return self.mapping.get(normalize_label(item), self.default_category)

    def unmapped(self, labels: Iterable[str]) -> List[str]:
        """Model labels that have NO entry in the mapping (useful startup check)."""
        return sorted(l for l in map(normalize_label, labels) if l not in self.mapping)
