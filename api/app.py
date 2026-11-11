"""
OPTIONAL minimal HTTP wrapper around the classification subsystem.

The Backend owner may call ``ClassificationService.classify()`` directly from
Python instead; this file only exists so the team can test with curl/Postman
and so the `POST /classify` requirement (FR-09) is covered.

Run:
    python -m api.app                       # http://127.0.0.1:5002
Test:
    curl -F "image=@bottle.jpg" http://127.0.0.1:5002/classify

Responses
---------
200  status "ok" or "uncertain"
400  invalid image / missing file            413  file too large
500  inference / unexpected failure          503  model not available
"""
from __future__ import annotations

from typing import Optional

from flask import Flask, jsonify, request

from waste_classification import ClassificationService
from waste_classification.schemas import ClassificationResult

# error_code -> HTTP status (anything not listed falls back to 400 for input errors, 500 otherwise)
HTTP_STATUS = {
    "FILE_TOO_LARGE": 413,
    "INVALID_IMAGE": 400,
    "UNSUPPORTED_FORMAT": 400,
    "IMAGE_TOO_SMALL": 400,
    "CORRUPTED_IMAGE": 400,
    "NO_FILE": 400,
    "MODEL_LOAD_FAILED": 503,
    "CONFIGURATION_ERROR": 500,
    "INFERENCE_FAILED": 500,
    "INTERNAL_ERROR": 500,
}


def create_app(service: Optional[ClassificationService] = None) -> Flask:
    """Application factory. Pass a ready service (used by tests) or let it build one."""
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024  # hard cap; the validator enforces the real limit
    holder = {"service": service}

    def get_service() -> ClassificationService:
        # Lazy loading: the model is loaded on first request, not at import time.
        if holder["service"] is None:
            holder["service"] = ClassificationService.from_settings()
        return holder["service"]

    @app.get("/health")
    def health():
        return jsonify({"status": "up"})

    @app.post("/classify")
    def classify():
        upload = request.files.get("image") or request.files.get("file")
        if upload is None:
            result = ClassificationResult.error(
                "NO_FILE", "Send the picture as multipart/form-data in the field 'image'")
        else:
            try:
                result = get_service().classify(upload.read())
            except Exception as exc:  # e.g. the model could not be loaded
                code = getattr(exc, "code", "INTERNAL_ERROR")
                result = ClassificationResult.error(code, getattr(exc, "message", str(exc)))
        status = HTTP_STATUS.get(result.error_code, 500) if result.is_error else 200
        return jsonify(result.to_dict()), status

    return app


if __name__ == "__main__":
    create_app().run(host="127.0.0.1", port=5002, debug=False)
