"""
Custom exceptions of the classification subsystem.

Every error carries a stable machine-readable ``code`` that ends up in the JSON
response (``error_code``). Other subsystems (Backend, Frontend) can therefore
react to errors without parsing human-readable messages.

Hierarchy
---------
ClassificationError
├── InvalidImageError            (input problems - the *user* can fix them)
│   ├── UnsupportedFormatError
│   ├── FileTooLargeError
│   ├── ImageTooSmallError
│   └── CorruptedImageError
├── ConfigurationError           (bad settings / mapping file)
├── ModelLoadError               (model files missing or unreadable)
└── InferenceError               (the model failed while predicting)
"""


class ClassificationError(Exception):
    """Base class of all errors raised by this subsystem."""

    code = "CLASSIFICATION_ERROR"

    def __init__(self, message: str = "") -> None:
        self.message = message or self.__class__.__name__
        super().__init__(self.message)


# --------------------------------------------------------------------------- #
# Input errors (caused by the uploaded image)
# --------------------------------------------------------------------------- #
class InvalidImageError(ClassificationError):
    """The uploaded data is not an acceptable image."""

    code = "INVALID_IMAGE"


class UnsupportedFormatError(InvalidImageError):
    """The image format is not in the allowed list (e.g. GIF, BMP)."""

    code = "UNSUPPORTED_FORMAT"


class FileTooLargeError(InvalidImageError):
    """The file exceeds the configured size limit."""

    code = "FILE_TOO_LARGE"


class ImageTooSmallError(InvalidImageError):
    """The image resolution is below the configured minimum."""

    code = "IMAGE_TOO_SMALL"


class CorruptedImageError(InvalidImageError):
    """The data is empty, truncated, or not a readable image at all."""

    code = "CORRUPTED_IMAGE"


# --------------------------------------------------------------------------- #
# Internal errors (not the user's fault)
# --------------------------------------------------------------------------- #
class ConfigurationError(ClassificationError):
    """Invalid settings or class-to-category mapping."""

    code = "CONFIGURATION_ERROR"


class ModelLoadError(ClassificationError):
    """The model could not be loaded (missing files, missing libraries...)."""

    code = "MODEL_LOAD_FAILED"


class InferenceError(ClassificationError):
    """The model raised an error while predicting."""

    code = "INFERENCE_FAILED"
