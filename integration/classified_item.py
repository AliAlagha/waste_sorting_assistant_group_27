# Adapter between the two subsystems:
# the classification gives labels like "brown-glass" and statuses "ok" / "uncertain",
# the recommendation rules know "glass" and ask get_item_name() / is_certain().

ITEM_ALIASES = {
    "brown-glass": "glass",
    "green-glass": "glass",
    "white-glass": "glass",
}


class ClassifiedItem:

    def __init__(self, item_name, confidence, min_confidence=0.6, label=None, model_version=""):
        self._item_name = ITEM_ALIASES.get(item_name, item_name)
        self._label = label or item_name          # the original model label
        self._confidence = confidence
        self._min_confidence = min_confidence
        self._model_version = model_version

    @classmethod
    def from_result(cls, result, min_confidence=0.6):
        # result = waste_classification.ClassificationResult
        confidence = result.confidence or 0.0
        # "uncertain" results are below the threshold, so is_certain() is False for them
        if result.status != "ok":
            min_confidence = max(min_confidence, confidence + 0.0001)
        return cls(result.item, confidence, min_confidence, result.item, result.model_version or "")

    # getters
    def get_item_name(self):
        return self._item_name

    def get_label(self):
        return self._label

    def get_confidence(self):
        return self._confidence

    def get_model_version(self):
        return self._model_version

    def get_status(self):
        return "Success" if self.is_certain() else "Uncertain"

    # other methods
    def is_certain(self):
        return self._confidence >= self._min_confidence

    def get_confidence_percent(self):
        return f"{round(self._confidence * 100)}%"

    def __str__(self):
        return f"{self._item_name} ({self.get_confidence_percent()}, {self.get_status()})"
