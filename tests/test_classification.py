# AI waste classification: upload validation, prediction, top-3, uncertainty, error handling
import pytest

from helpers import make_classification, make_image
from waste_classification import CategoryMapper


def test_photo_is_classified_with_top3():
    result = make_classification().classify(make_image())
    assert (result.status, result.item, result.category, result.confidence) == ("ok", "plastic", "recyclable", 0.9)
    assert [p.item for p in result.top_predictions] == ["plastic", "paper", "metal"]


def test_low_confidence_is_uncertain():
    result = make_classification({"plastic": 0.4, "paper": 0.35, "metal": 0.25}).classify(make_image())
    assert result.status == "uncertain" and "retake the photo" in result.message


@pytest.mark.parametrize("data, code", [
    (b"this is not a photo", "CORRUPTED_IMAGE"),
    (make_image(size=(20, 20)), "IMAGE_TOO_SMALL"),
    (make_image(fmt="GIF"), "UNSUPPORTED_FORMAT"),
    (b"x" * (2 * 1024 * 1024), "FILE_TOO_LARGE"),
])
def test_invalid_upload_gives_an_error_code(data, code):
    result = make_classification().classify(data)
    assert result.status == "error" and result.error_code == code


def test_model_crash_gives_an_error_result():
    assert make_classification(fail=True).classify(make_image()).error_code == "INFERENCE_FAILED"


def test_label_is_mapped_to_a_category():
    mapper = CategoryMapper({"brown-glass": "recyclable"})
    assert mapper.to_category("Brown_Glass") == "recyclable"
    assert mapper.to_category("pizza") == "landfill"          # unknown labels use the default category
