from .errors import RecommendationError

CATEGORIES = ["Recyclable", "Compostable", "Landfill"]


class RecyclingRule:

    def __init__(self, item_name, category, bin_name, tip=""):
        self._item_name = item_name
        self._category = ""
        self.set_category(category)
        self._bin_name = bin_name
        self._tip = tip

    # item name
    def get_item_name(self):
        return self._item_name

    def set_item_name(self, item_name):
        self._item_name = item_name

    # category
    def get_category(self):
        return self._category

    def set_category(self, category):
        if category not in CATEGORIES:
            raise RecommendationError("unknown category: " + category)
        self._category = category

    # bin
    def get_bin_name(self):
        return self._bin_name

    def set_bin_name(self, bin_name):
        self._bin_name = bin_name

    # tip
    def get_tip(self):
        return self._tip

    def set_tip(self, tip):
        self._tip = tip

    # functions
    def is_recyclable(self):
        return self._category == "Recyclable"

    def has_tip(self):
        return self._tip != ""

    def show(self):
        print(self._item_name + " -> " + self._category + " -> " + self._bin_name)
