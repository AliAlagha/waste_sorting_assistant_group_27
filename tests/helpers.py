# fakes for the tests: a fixed AI model, the OpenAI client and the EDG website (no internet needed)
import io
import json

from PIL import Image

from waste_classification import (CategoryMapper, ClassificationService, ImageClassifierBackend, ImageValidator,
                                  WasteClassifier)


def make_image(fmt="PNG", size=(128, 128), color=(30, 160, 60)):
    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, format=fmt)
    return buffer.getvalue()


class FixedBackend(ImageClassifierBackend):
    # fake model: always gives the same scores (or crashes)
    version = "fixed-test-model"

    def __init__(self, scores, fail=False):
        self.scores = scores
        self.fail = fail

    def predict_scores(self, image):
        if self.fail:
            raise RuntimeError("model crashed")
        return self.scores


def make_classification(scores=None, fail=False):
    scores = scores or {"plastic": 0.9, "paper": 0.06, "metal": 0.04}
    mapper = CategoryMapper({"plastic": "recyclable", "paper": "recyclable", "metal": "recyclable",
                             "biological": "compostable", "brown-glass": "recyclable", "trash": "landfill"})
    return ClassificationService(ImageValidator(1, 64), WasteClassifier(FixedBackend(scores, fail)), mapper, 0.6, 3)


class FakeOpenAI:
    # same shape as the answer of the openai library
    def __init__(self, text="Rinse and recycle.", fail=False):
        self.text = text
        self.fail = fail
        self.chat = self
        self.completions = self

    def create(self, **kwargs):
        if self.fail:
            raise ConnectionError("no internet")
        message = type("Message", (), {"content": self.text})
        return type("Response", (), {"choices": [type("Choice", (), {"message": message})]})


# ---------- fake EDG website (Sonnenstr. 94, 96, 96 a) ----------
# same format as a real EDG calendar; Wertstoffe on 5 Dec is a Saturday (holiday shift)
EDG_ICS = "\r\n".join(["BEGIN:VCALENDAR"] + [
    "BEGIN:VEVENT\r\nDTSTART;VALUE=DATE:" + day + "\r\nSUMMARY;LANGUAGE=de:" + title + "\r\nEND:VEVENT"
    for day, title in [
        ("20261103", "Restabfall 1100 l 01-wöchentl."), ("20261110", "Restabfall 1100 l 01-wöchentl."),
        ("20261106", "Wertstoffe 1100 l 02-wöchentl."), ("20261120", "Wertstoffe 1100 l 02-wöchentl."),
        ("20261205", "Wertstoffe 1100 l 02-wöchentl."),
        ("20261113", "Bioabfall 240 l 02-wöchentl."), ("20261127", "Bioabfall 240 l 02-wöchentl."),
        ("20261110", "Altpapier 1100 l 04-wöchentl."), ("20261208", "Altpapier 1100 l 04-wöchentl."),
    ]] + ["END:VCALENDAR"])
FORM_PAGE = """<form><input type="hidden" name="SessionId" value="abc">
<select name="Ort"><option value="" selected></option><option value="S">S</option></select>
<select name="Strasse"><option value="" selected></option></select>
<select name="Hausnummer"><option value="" selected></option></select></form>"""
RESULT_PAGE = ('<a href="WasteManagementServiceServlet?ApplicationName=Calendar&amp;SubmitAction=sync'
               '&amp;StandortID=1&amp;AboID=2">URL</a>')


class FakeResponse:
    def __init__(self, text):
        self.text = text

    def raise_for_status(self):
        pass


class FakeEdg:
    # plays the EDG form: first letter -> streets -> house numbers -> result page -> calendar
    def get(self, url, params=None, headers=None, timeout=None):
        return FakeResponse(EDG_ICS if "StandortID=1&AboID=2" in url else FORM_PAGE)

    def post(self, url, data=None, files=None, headers=None, timeout=None):
        if files is not None:
            return FakeResponse(RESULT_PAGE)
        action = dict(pair.split("=", 1) for pair in data.decode("utf-8").split("&"))["SubmitAction"]
        if action == "CITYCHANGED":
            values = [{"name": "Strasse", "items": [{"item": "Schwanenwall"}, {"item": "Sonnenstr."}]}]
        else:
            values = [{"name": "Hausnummer", "items": [{"item": "94"}, {"item": "96"}, {"item": "96 a"}]}]
        return FakeResponse(json.dumps({"Response": {"values": values}}))


class BrokenEdg(FakeEdg):
    # EDG is not reachable
    def get(self, url, params=None, headers=None, timeout=None):
        import requests
        raise requests.ConnectionError("no internet")
