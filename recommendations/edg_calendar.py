import html
import json
import re
import sys
from datetime import date, datetime
from html.parser import HTMLParser

import requests

from .errors import RecommendationError

# In Dortmund the collection dates depend on street + house number.
# EDG (Entsorgung Dortmund GmbH) has a form for this on www.edg.de.
# This class fills in that form like a browser does and reads the calendar:
#   1. open the form page
#   2. send the first letter of the street      -> EDG sends the list of streets
#   3. send the street                          -> EDG sends the list of house numbers
#   4. send the house number and press "weiter" -> result page with the dates of this house number
#   5. only if the page shows no dates: download the calendar (iCal file)

PORTAL = "https://kundenportal.edg.de/WasteManagementDortmund/"
SERVLET = PORTAL + "WasteManagementServlet"
HEADERS = {"User-Agent": "Mozilla/5.0 (student project: waste sorting assistant)"}
AJAX_HEADERS = {**HEADERS, "Content-Type": "text/plain; charset=UTF-8", "X-Requested-With": "XMLHttpRequest"}
DAYS_SHORT = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
SYNC_LINK = re.compile(r"WasteManagementServiceServlet\?[^\"'<>\s]*?StandortID=\d+[^\"'<>\s]*")

# first word of the EDG event -> our bin
EDG_BINS = {
    "restabfall": "Grey bin",
    "bioabfall": "Brown bin",
    "altpapier": "Blue bin",
    "wertstoffe": "Yellow bin",
}


class FormParser(HTMLParser):
    # collects the values a browser would send (hidden inputs and selects)

    def __init__(self):
        super().__init__()
        self.fields = {}
        self._select = None
        self._first = True

    def handle_starttag(self, tag, attrs):
        attrs = {k.lower(): (v or "") for k, v in attrs}
        name = attrs.get("name") or attrs.get("id")
        if tag == "input" and name and attrs.get("type", "text").lower() not in ("button", "submit"):
            self.fields[name] = attrs.get("value", "")
        elif tag == "select" and name:
            self._select = name
            self._first = True
            self.fields[name] = ""
        elif tag == "option" and self._select:
            if self._first or "selected" in attrs:
                self.fields[self._select] = attrs.get("value", "")
            self._first = False

    def handle_endtag(self, tag):
        if tag == "select":
            self._select = None


def normalize_street(street):
    # "Sonnenstr.", "SONNENSTRASSE" and "Sonnen-Straße" are the same street
    street = street.strip().lower().replace("ß", "ss")
    street = re.sub(r"str\.?$", "strasse", street)
    street = re.sub(r"str\.\s*", "strasse", street)
    return re.sub(r"[\s\-.]", "", street)


def house_key(number):
    # "2 b - 2 c" -> "2b-2c" (spaces never matter)
    return re.sub(r"\s", "", number).lower()


def pick_house_number(wanted, numbers):
    wanted = house_key(wanted)
    exact = [n for n in numbers if house_key(n) == wanted]
    if exact:
        return exact
    if not wanted.isdigit():
        # "4 a" or "2 b-2c": only the same building, never a different one
        return [n for n in numbers if house_key(n).split("-")[0] == wanted.split("-")[0]
                and house_key(n).startswith(wanted)]
    # "38": no "38" in the list, so "38 a", "38-44" or a range like "29 -39" is used
    number = int(wanted)
    same = []
    in_range = []
    for n in numbers:
        found = re.match(r"\s*(\d+)\s*(?:-\s*(\d+))?", n)
        if found is None:
            continue
        first = int(found.group(1))
        last = int(found.group(2)) if found.group(2) else first
        if first == number:
            same.append(n)
        elif first <= number <= last:
            in_range.append(n)
    return same or in_range


def street_letter(street):
    # the EDG form has "I." and "II." for streets like "I. Bickestr." and "II. Rosenterrasse"
    found = re.match(r"\s*(II?)\.", street)
    if found:
        return found.group(1) + "."
    return street.strip()[0].upper()


def rhythm_weeks(title):
    # "Altpapier 240 l 04-wöchentl." -> 4
    found = re.search(r"(\d+)\s*-\s*w(?:ö|oe|o)chentl", title, re.IGNORECASE)
    if found:
        return int(found.group(1))
    return 0


def parse_ics(text):
    # returns a sorted list of (date, bin name, EDG title)
    if "BEGIN:VCALENDAR" not in text:
        raise RecommendationError("EDG did not send a calendar")
    events = []
    day = None
    title = ""
    for line in text.splitlines():
        if line.startswith("BEGIN:VEVENT"):
            day = None
            title = ""
        elif line.startswith("DTSTART"):
            day = datetime.strptime(line.split(":", 1)[1].strip()[:8], "%Y%m%d").date()
        elif line.startswith("SUMMARY"):
            title = line.split(":", 1)[1].strip()
        elif line.startswith("END:VEVENT") and day and title:
            first_word = title.split()[0].lower()
            if first_word in EDG_BINS:
                events.append((day, EDG_BINS[first_word], title))
    events.sort()
    return events


def _field(page, name):
    # text of <P ID="name">text</P> on the EDG result page
    found = re.search(r'ID="' + re.escape(name) + r'"[^>]*>([^<]*)<', page, re.IGNORECASE)
    if found is None:
        return ""
    return html.unescape(found.group(1)).strip()


def parse_result_page(page):
    # The result page shows only the containers of this house number (the iCal file can also
    # contain the bins of the other house numbers of the same building) and more dates.
    # Each container has a key like "R[1100](01-w)" and fields Label..., Tonnenart..., Turnus...
    # and TermineDatum..._1, _2, ... ("Mi. 11.11.2026" or "Di. 22.12.2026 *" for a holiday change).
    events = []
    for key, label in re.findall(r'ID="Label([^"]+)"[^>]*>([^<]*)<', page, re.IGNORECASE):
        label = html.unescape(label).strip()
        if label == "" or label.split()[0].lower() not in EDG_BINS:
            continue
        title = " ".join(part for part in (label, _field(page, "Tonnenart" + key), _field(page, "Turnus" + key))
                         if part)
        pattern = r'ID="TermineDatum' + re.escape(key) + r'_\d+"[^>]*>[^<\d]*(\d\d\.\d\d\.\d{4})'
        for text in re.findall(pattern, page, re.IGNORECASE):
            day = datetime.strptime(text, "%d.%m.%Y").date()
            events.append((day, EDG_BINS[label.split()[0].lower()], title))
    events.sort()
    return events


class EdgCalendar:

    def __init__(self, session=None, timeout=15):
        self._session = session or requests.Session()
        self._timeout = timeout
        self.last_ics = ""
        self.last_address = ""      # street + house number exactly as EDG writes them
        self.last_result_page = ""  # HTML of the EDG result page (for checking)

    def _ajax(self, fields, action):
        # the EDG page sends these steps as text "name=value&name=value"
        fields = dict(fields)
        fields.update({"SubmitAction": action, "Ajax": "TRUE", "AjaxOnPage": "false"})
        body = "&".join(k + "=" + str(v).replace("&", "%26").replace("=", "%3D") for k, v in fields.items())
        response = self._session.post(SERVLET, data=body.encode("utf-8"), headers=AJAX_HEADERS,
                                      timeout=self._timeout)
        response.raise_for_status()
        return response.text

    def _choices(self, answer, field):
        # EDG answers with JSON: {"Response": {"values": [{"name": ..., "items": [{"item": ...}]}]}}
        try:
            data = json.loads(answer.replace("\n", "").replace("\r", ""))
        except ValueError:
            raise RecommendationError("EDG answered in an unexpected format")
        for value in data.get("Response", {}).get("values", []):
            if value.get("name") == field:
                return [item.get("item", "") for item in value.get("items", []) if item.get("item", "").strip()]
        return []

    def fetch_result_page(self, street, house_number):
        try:
            return self._result_page(street.strip(), str(house_number).strip())
        except requests.RequestException as error:
            raise RecommendationError("EDG can not be reached: " + str(error))

    def fetch_ics(self, street, house_number):
        result = self.fetch_result_page(street, house_number)
        try:
            return self._download_ics(result, street + " " + str(house_number))
        except requests.RequestException as error:
            raise RecommendationError("EDG can not be reached: " + str(error))

    # lists for the address form of the web app (steps 1-3 below, EDG's own spelling)
    def get_streets(self, letter):
        try:
            fields = self._form_fields()
            fields["Ort"] = street_letter(letter)
            return self._choices(self._ajax(fields, "CITYCHANGED"), "Strasse")
        except requests.RequestException as error:
            raise RecommendationError("EDG can not be reached: " + str(error))

    def get_house_numbers(self, street):
        try:
            fields = self._form_fields()
            fields["Ort"] = street_letter(street)
            self._ajax(fields, "CITYCHANGED")
            fields["Strasse"] = street
            return self._choices(self._ajax(fields, "STREETCHANGED"), "Hausnummer")
        except requests.RequestException as error:
            raise RecommendationError("EDG can not be reached: " + str(error))

    def _form_fields(self):
        response = self._session.get(SERVLET, params={"SubmitAction": "wasteDisposalServices", "InFrameMode": "TRUE"},
                                     headers=HEADERS, timeout=self._timeout)
        response.raise_for_status()
        parser = FormParser()
        parser.feed(response.text)
        return parser.fields

    def _result_page(self, street, house_number):
        if street == "" or house_number == "":
            raise RecommendationError("street and house number are needed")
        # 1. form page
        response = self._session.get(SERVLET, params={"SubmitAction": "wasteDisposalServices", "InFrameMode": "TRUE"},
                                     headers=HEADERS, timeout=self._timeout)
        response.raise_for_status()
        parser = FormParser()
        parser.feed(response.text)
        fields = parser.fields

        # 2. first letter -> streets (we take EDG's own spelling of the street)
        fields["Ort"] = street_letter(street)
        streets = self._choices(self._ajax(fields, "CITYCHANGED"), "Strasse")
        matches = [s for s in streets if normalize_street(s) == normalize_street(street)]
        if not matches:
            raise RecommendationError("EDG does not know the street " + street)
        fields["Strasse"] = matches[0]

        # 3. street -> house numbers
        numbers = self._choices(self._ajax(fields, "STREETCHANGED"), "Hausnummer")
        matches = pick_house_number(house_number, numbers)
        if not matches:
            raise RecommendationError("EDG does not know house number " + house_number + " in " + fields["Strasse"]
                                      + ". EDG knows: " + ", ".join(numbers[:40]))
        fields["Hausnummer"] = matches[0]
        self.last_address = fields["Strasse"] + " " + fields["Hausnummer"]

        # 4. "weiter" -> result page (normal form, sent as multipart)
        fields.update({"SubmitAction": "forward", "Ajax": "false", "AjaxOnPage": "false"})
        files = {k: (None, str(v)) for k, v in fields.items()}
        response = self._session.post(SERVLET, files=files, headers=HEADERS, timeout=self._timeout)
        response.raise_for_status()
        self.last_result_page = response.text
        return response.text

    def _download_ics(self, result, address):
        # 5a. calendar link on the result page
        link = SYNC_LINK.search(result)
        if link:
            response = self._session.get(PORTAL + html.unescape(link.group(0)), headers=HEADERS,
                                         timeout=self._timeout)
            response.raise_for_status()
            if "BEGIN:VCALENDAR" in response.text:
                return response.text

        # 5b. download button of the result page
        parser = FormParser()
        parser.feed(result)
        download = parser.fields
        download.update({"SubmitAction": "filedownload_ICAL", "Ajax": "TRUE", "AjaxOnPage": "false"})
        download.setdefault("ICalErinnerung", "keine Erinnerung")
        download.setdefault("ICalZeit", "18:00 Uhr")
        response = self._session.post(SERVLET, data=download, headers=HEADERS, timeout=self._timeout)
        response.raise_for_status()
        if "BEGIN:VCALENDAR" in response.text:
            return response.text
        raise RecommendationError("EDG sent no calendar for " + address)

    def get_events(self, street, house_number):
        # 1) the dates on the result page (only this house number, holiday changes included)
        # 2) if the page has none, the iCal file
        result = self.fetch_result_page(street, house_number)
        self.last_ics = ""
        events = parse_result_page(result)
        if events:
            return events
        try:
            self.last_ics = self._download_ics(result, street + " " + str(house_number))
        except requests.RequestException as error:
            raise RecommendationError("EDG can not be reached: " + str(error))
        return parse_ics(self.last_ics)


# test it alone:  python -m recommendations.edg_calendar "Sonnenstraße" 96 [--save]
if __name__ == "__main__":
    from .collection_schedule import CollectionSchedule

    if len(sys.argv) < 3:
        print('Usage: python -m recommendations.edg_calendar "<street>" <house number> [--save]')
        sys.exit(1)
    # everything after the street is the house number, so 4 a and "4 a" both work
    street = sys.argv[1]
    house_number = " ".join(arg for arg in sys.argv[2:] if arg != "--save")
    calendar = EdgCalendar()
    schedule = CollectionSchedule("Dortmund")
    try:
        schedule.load_address(street, house_number, calendar)
    except RecommendationError as error:
        print("Error:", error)
        sys.exit(2)
    schedule.show()
    events = parse_result_page(calendar.last_result_page) or parse_ics(calendar.last_ics)
    print(len(events), "dates from EDG, the first ones:")
    for day, bin_name, title in events[:12]:
        print("  ", day, DAYS_SHORT[day.weekday()], bin_name, "-", title)
    if "--save" in sys.argv:
        file_name = "edg_" + normalize_street(street) + "_" + house_number.replace(" ", "") + ".ics"
        with open(file_name.replace(".ics", ".html"), "w", encoding="utf-8") as file:
            file.write(calendar.last_result_page)
        print("EDG result page saved in", file_name.replace(".ics", ".html"))
    print("Today is", date.today(), "- compare these dates with the EDG Abfallkalender on www.edg.de")
