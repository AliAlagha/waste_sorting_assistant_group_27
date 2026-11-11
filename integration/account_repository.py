from sqlalchemy import delete, insert, select, update
from sqlalchemy.exc import IntegrityError

from .account import Account
from .database import users
from .errors import IntegrationError


class AccountRepository:
    # saves the accounts in the table users

    def __init__(self, database):
        self._database = database

    def add(self, account):
        try:
            with self._database.get_engine().begin() as connection:
                result = connection.execute(insert(users).values(
                    username=account.get_username(), password_hash=account.get_password_hash(),
                    role=account.get_role(), region_name=account.get_region_name(), street=account.get_street(),
                    house_number=account.get_house_number(), created_at=account.get_created_at()))
        except IntegrityError:
            raise IntegrationError("username {} is already taken".format(account.get_username()), 409)
        account.set_user_id(result.inserted_primary_key[0])
        return account

    def find_by_username(self, username):
        with self._database.get_engine().connect() as connection:
            row = connection.execute(select(users).where(users.c.username == username)).mappings().first()
        return self._to_account(row) if row else None

    def find_by_id(self, user_id):
        with self._database.get_engine().connect() as connection:
            row = connection.execute(select(users).where(users.c.user_id == user_id)).mappings().first()
        return self._to_account(row) if row else None

    def update(self, account):
        with self._database.get_engine().begin() as connection:
            connection.execute(update(users).where(users.c.user_id == account.get_user_id()).values(
                password_hash=account.get_password_hash(), role=account.get_role(), region_name=account.get_region_name(),
                street=account.get_street(), house_number=account.get_house_number()))

    def delete(self, user_id):
        with self._database.get_engine().begin() as connection:
            connection.execute(delete(users).where(users.c.user_id == user_id))

    def find_all(self):
        with self._database.get_engine().connect() as connection:
            rows = connection.execute(select(users).order_by(users.c.role, users.c.username)).mappings().all()
        return [self._to_account(row) for row in rows]

    def count(self):
        with self._database.get_engine().connect() as connection:
            return len(connection.execute(select(users.c.user_id)).all())

    def _to_account(self, row):
        return Account(row["username"], None, row["role"], row["region_name"], row["street"], row["house_number"],
                       user_id=row["user_id"], password_hash=row["password_hash"], created_at=row["created_at"])
