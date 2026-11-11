from .collection_schedule import CollectionSchedule
from .errors import RecommendationError
from .recommendation import Recommendation
from .recycling_rule import RecyclingRule


class RecommendationService:

    def __init__(self, region_name="Dortmund"):
        self._region_name = region_name
        self._rules = {}
        self._schedule = CollectionSchedule(region_name)    # used when the user gave no address
        self._address_schedules = {}                         # (street, house number) -> CollectionSchedule
        self._calendar = None                                # EdgCalendar, created when it is needed
        self._history = []

    def load_rules(self):
        # rules for Dortmund, other cities can come later
        # real rules of EDG Entsorgung Dortmund (Abfall-ABC 2025)
        self.add_rule(RecyclingRule("plastic", "Recyclable", "Yellow bin", "Empty it, no need to wash it"))
        self.add_rule(RecyclingRule("metal", "Recyclable", "Yellow bin", "Empty the can"))
        self.add_rule(RecyclingRule("paper", "Recyclable", "Blue bin", "No dirty or coated paper"))
        self.add_rule(RecyclingRule("cardboard", "Recyclable", "Blue bin", "Flatten the box"))
        self.add_rule(RecyclingRule("glass", "Recyclable", "Glass container",
                                    "Sort by colour (white, green, brown), no window glass or ceramics"))
        self.add_rule(RecyclingRule("clothes", "Recyclable", "Clothes container", "Only clean clothes in a closed bag"))
        self.add_rule(RecyclingRule("shoes", "Recyclable", "Clothes container", "Tie the pair together"))
        self.add_rule(RecyclingRule("biological", "Compostable", "Brown bin",
                                    "No plastic bags, also not 'compostable' ones"))
        self.add_rule(RecyclingRule("battery", "Landfill", "Battery collection point",
                                    "Never put it in a household bin, shops take batteries back for free"))
        self.add_rule(RecyclingRule("trash", "Landfill", "Grey bin"))
        self._schedule.load_default_days()

    # region
    def get_region_name(self):
        return self._region_name

    def set_region_name(self, region_name):
        self._region_name = region_name
        self._schedule.set_region_name(region_name)

    # address: the collection dates in Dortmund depend on street + house number
    def set_address(self, street, house_number, calendar=None):
        self._schedule.load_address(street, house_number, calendar)

    def set_calendar(self, calendar):
        # tests use a fake EDG website here
        self._calendar = calendar

    def get_schedule_for(self, street, house_number):
        # every address is asked at EDG only once
        key = (street.strip().lower(), str(house_number).strip().lower())
        if key not in self._address_schedules:
            schedule = CollectionSchedule(self._region_name)
            if self._calendar is None:
                from .edg_calendar import EdgCalendar
                self._calendar = EdgCalendar()
            schedule.load_address(street, house_number, self._calendar)   # RecommendationError if EDG fails
            self._address_schedules[key] = schedule
        return self._address_schedules[key]

    # rules, schedule and history (only getters)
    def get_rules(self):
        return self._rules

    def get_schedule(self):
        return self._schedule

    def get_history(self):
        return self._history

    # functions
    def add_rule(self, rule):
        self._rules[rule.get_item_name()] = rule

    def remove_rule(self, item_name):
        if item_name not in self._rules:
            raise RecommendationError("there is no rule for " + item_name)
        del self._rules[item_name]

    def get_rule_count(self):
        return len(self._rules)

    def find_rules_by_category(self, category):
        found = []
        for item_name in self._rules:
            if self._rules[item_name].get_category() == category:
                found.append(self._rules[item_name])
        return found

    def recommend(self, result, street="", house_number=""):
        # we need the result of the classification, nothing else
        # any classification result with get_item_name() and is_certain() works
        if not hasattr(result, "get_item_name") or not hasattr(result, "is_certain"):
            raise RecommendationError("recommend() needs a classification result")
        if len(self._rules) == 0:
            raise RecommendationError("no rules loaded for " + self._region_name)
        item = result.get_item_name()
        # AI not sure or item unknown -> grey bin (general waste) is the safe choice
        if not result.is_certain() or item not in self._rules:
            rule = RecyclingRule(item, "Landfill", "Grey bin", "Not sure? ask your local waste authority")
        else:
            rule = self._rules[item]
        # dates of the user's address; if EDG can not help, only the rhythm is shown
        schedule = self._schedule
        if street != "" and str(house_number) != "":
            schedule = self.get_schedule_for(street, house_number)
        bin_name = rule.get_bin_name()
        recommendation = Recommendation(rule, self._region_name,
                                        schedule.get_pickup_day(bin_name),
                                        schedule.get_rhythm_text(bin_name),
                                        schedule.get_next_pickup(bin_name))
        self._history.append(recommendation)
        return recommendation
