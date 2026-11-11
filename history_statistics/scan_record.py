from datetime import datetime

from .errors import StatisticsError

CATEGORIES = ["Recyclable", "Compostable", "Landfill"]


class ScanRecord:
    # one scan as it is saved in the table scan_records
    # no personal data: only the region, never the address or the photo

    def __init__(self, scan_id, region_name, category, item_name, scan_date=None,
                 bin_name="", confidence=None, status="ok", user_id=None):
        self._scan_id = scan_id
        self._region_name = region_name
        self._category = ""
        self.set_category(category)
        self._item_name = item_name
        # no date given means the scan is from now
        if scan_date is None:
            scan_date = datetime.now()
        self._scan_date = scan_date
        self._bin_name = bin_name
        self._confidence = confidence
        self._status = status
        self._user_id = user_id   # only used for "my history", removed when the user deletes the account

    # getters and setters

    def get_scan_id(self):
        return self._scan_id

    def set_scan_id(self, scan_id):
        self._scan_id = scan_id

    def get_region_name(self):
        return self._region_name

    def set_region_name(self, region_name):
        self._region_name = region_name

    def get_category(self):
        return self._category

    def set_category(self, category):
        if category not in CATEGORIES:
            raise StatisticsError("unknown category: " + str(category))
        self._category = category

    def get_item_name(self):
        return self._item_name

    def get_bin_name(self):
        return self._bin_name

    def get_confidence(self):
        return self._confidence

    def get_status(self):
        return self._status

    def get_user_id(self):
        return self._user_id

    # methods

    def is_from_today(self):
        return self._scan_date.date() == datetime.now().date()

    def to_dict(self):
        return {
            "scan_id": self._scan_id,
            "region_name": self._region_name,
            "category": self._category,
            "item_name": self._item_name,
            "bin_name": self._bin_name,
            "confidence": self._confidence,
            "status": self._status,
            "scan_date": self._scan_date,
        }
