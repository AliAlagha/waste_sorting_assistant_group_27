from datetime import datetime

from werkzeug.security import check_password_hash, generate_password_hash

from .address_directory import REGIONS
from .errors import IntegrationError


class Account:
    ROLES = ["citizen", "municipality", "admin"]

    def __init__(self, username, password, role, region_name, street="", house_number="",
                 user_id=None, password_hash=None, created_at=None):
        if len(username.strip()) < 3:
            raise IntegrationError("username needs at least 3 characters", 400)
        self._user_id = user_id
        self._username = username.strip()
        self._password_hash = ""
        self._role = ""
        self.set_role(role)
        self._region_name = ""
        self.set_region_name(region_name)
        self._street = street.strip()                  # address is needed for the collection dates
        self._house_number = str(house_number).strip()
        self._created_at = created_at or datetime.now()
        if password_hash is not None:
            self._password_hash = password_hash        # loaded from the database
        else:
            self.set_password(password)

    # accessors
    def get_user_id(self):
        return self._user_id

    def get_username(self):
        return self._username

    def get_password_hash(self):
        return self._password_hash

    def get_role(self):
        return self._role

    def get_region_name(self):
        return self._region_name

    def get_street(self):
        return self._street

    def get_house_number(self):
        return self._house_number

    def get_created_at(self):
        return self._created_at

    # mutators
    def set_user_id(self, user_id):
        self._user_id = user_id

    def set_password(self, password):
        if password is None or len(password) < 6:
            raise IntegrationError("password needs at least 6 characters", 400)
        # only a salted hash is saved, never the password
        self._password_hash = generate_password_hash(password)

    def set_role(self, role):
        if role not in Account.ROLES:
            raise IntegrationError("unknown role: " + str(role), 400)
        self._role = role

    def set_region_name(self, region_name):
        # a fixed list, so "dortmund " and "Dortmund" are always the same region in the statistics
        region_name = (region_name or "").strip().title()
        if region_name not in REGIONS:
            raise IntegrationError("please choose a city from the list", 400)
        self._region_name = region_name

    def set_address(self, street, house_number):
        self._street = street
        self._house_number = str(house_number)

    # behaviour
    def check_password(self, password):
        return check_password_hash(self._password_hash, password or "")

    def is_admin(self):
        return self._role == "admin"

    def is_municipality(self):
        return self._role == "municipality"

    def has_address(self):
        return self._street != "" and self._house_number != ""

    def to_dict(self):
        return {"user_id": self._user_id, "username": self._username, "role": self._role,
                "region_name": self._region_name, "street": self._street, "house_number": self._house_number,
                "created_at": self._created_at.strftime("%Y-%m-%d")}
