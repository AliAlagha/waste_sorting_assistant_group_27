from recommendations.collection_schedule import CollectionSchedule
from recommendations.edg_calendar import normalize_street
from recommendations.errors import RecommendationError

from .errors import IntegrationError

# cities a user can choose (the scans are counted per city); collection days exist only for Dortmund (EDG)
REGIONS = ["Dortmund", "Bochum", "Essen", "Gelsenkirchen", "Hagen", "Unna"]
EDG_REGION = "Dortmund"


class AddressDirectory:
    # addresses of Dortmund from EDG: lists for the address form (kept in memory) and the check of an address

    def __init__(self):
        self._calendar = None                        # EdgCalendar used for the address check
        self._calendar_factory = None                # gives a new EDG session for every list lookup
        self._streets = {}                           # first letter -> streets
        self._numbers = {}                           # street -> house numbers

    def set_calendar(self, calendar, calendar_factory):
        self._calendar = calendar
        self._calendar_factory = calendar_factory

    def get_regions(self):
        return REGIONS

    def get_streets(self, text):
        text = (text or "").strip()
        if not text:
            return []
        letter = text[:3] if text[:2] in ("I.", "II") else text[0].upper()
        if letter not in self._streets:
            self._streets[letter] = self._ask(lambda calendar: calendar.get_streets(letter))
        return [street for street in self._streets[letter] if street.lower().startswith(text.lower())]

    def get_house_numbers(self, street):
        street = (street or "").strip()
        if not street:
            return []
        if street not in self._numbers:
            self._numbers[street] = self._ask(lambda calendar: calendar.get_house_numbers(street))
        return self._numbers[street]

    def check_address(self, region_name, street, house_number):
        # the collection days come from EDG, so a saved address must be one that EDG knows;
        # returns (street, house number) with the street in EDG's spelling, e.g. "Sonnenstraße" -> "Sonnenstr."
        street, house_number = (street or "").strip(), str(house_number or "").strip()
        if not street and not house_number:
            return "", ""
        if not street or not house_number:
            raise IntegrationError("please choose both street and house number, or neither", 400)
        if region_name != EDG_REGION:
            raise IntegrationError("collection days are only available for addresses in Dortmund (EDG)", 400)
        try:
            CollectionSchedule(region_name).load_address(street, house_number, self._calendar)
        except RecommendationError as error:
            raise IntegrationError(str(error), 503 if "can not be reached" in str(error) else 400)
        same = [s for s in self.get_streets(street[0]) if normalize_street(s) == normalize_street(street)]
        return (same[0] if same else street), house_number

    def _ask(self, question):
        try:
            return question(self._calendar_factory())
        except RecommendationError as error:
            raise IntegrationError(str(error), 503)
