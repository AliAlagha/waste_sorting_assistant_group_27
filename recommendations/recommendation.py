from datetime import datetime


class Recommendation:

    def __init__(self, rule, region_name, pickup_day="", rhythm="", next_pickup=None):
        self._rule = rule
        self._region_name = region_name
        self._pickup_day = pickup_day
        self._rhythm = rhythm              # e.g. "every 2 weeks"
        self._next_pickup = next_pickup    # date of the next collection or None
        self._created_at = datetime.now()

    # rule
    def get_rule(self):
        return self._rule

    def set_rule(self, rule):
        self._rule = rule

    # region
    def get_region_name(self):
        return self._region_name

    def set_region_name(self, region_name):
        self._region_name = region_name

    # pickup day
    def get_pickup_day(self):
        return self._pickup_day

    def set_pickup_day(self, pickup_day):
        self._pickup_day = pickup_day

    # rhythm and next pickup (only getters, they come from the schedule)
    def get_rhythm(self):
        return self._rhythm

    def get_next_pickup(self):
        return self._next_pickup

    # created at (only getter, it should not change)
    def get_created_at(self):
        return self._created_at

    # short cuts so we dont need get_rule() every time
    def get_category(self):
        return self._rule.get_category()

    def get_bin_name(self):
        return self._rule.get_bin_name()

    # functions
    def to_dict(self):
        return {
            "item_name": self._rule.get_item_name(),
            "category": self._rule.get_category(),
            "bin_name": self._rule.get_bin_name(),
            "tip": self._rule.get_tip(),
            "pickup_day": self._pickup_day,
            "rhythm": self._rhythm,
            "next_pickup": str(self._next_pickup) if self._next_pickup else "",
            "region_name": self._region_name,
        }

    def show(self):
        self._rule.show()
        if self._rule.has_tip():
            print("  Tip: " + self._rule.get_tip())
        if self._next_pickup is None and self._rhythm != "" and self._rhythm is not None:
            print("  Pickup: " + self._pickup_day + ", " + self._rhythm + " (" + self._region_name + ")")
        elif self._next_pickup is None:
            print("  Pickup: " + self._pickup_day + " (" + self._region_name + ")")
        else:
            print("  Pickup: " + self._pickup_day + ", " + self._rhythm + ", next " + str(self._next_pickup)
                  + " (" + self._region_name + ")")
