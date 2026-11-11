from .account import Account
from .errors import IntegrationError
from .session import Session


class AccountService:
    # accounts, login sessions and the administration of users and roles

    def __init__(self, accounts, scans, addresses):
        self._accounts = accounts          # AccountRepository (table users)
        self._scans = scans                # ScanRepository, to anonymise the scans of a deleted user
        self._addresses = addresses        # AddressDirectory, to check an address with EDG
        self._sessions = {}                # token -> Session (in memory)

    # ---------- register, log in, log out ----------
    def register(self, username, password, role, region_name, street="", house_number=""):
        account = Account(username, password, role, region_name)
        account.set_address(*self._addresses.check_address(account.get_region_name(), street, house_number))
        return self._accounts.add(account)

    def ensure_account(self, username, password, role, region_name, street="", house_number=""):
        # used for the demo accounts: create them only once
        account = self._accounts.find_by_username(username)
        if account is None:
            account = self.register(username, password, role, region_name, street, house_number)
        return account

    def login(self, username, password):
        account = self._accounts.find_by_username((username or "").strip())
        if account is None or not account.check_password(password):
            raise IntegrationError("wrong username or password", 401)
        session = Session(account)
        self._sessions[session.get_token()] = session
        return session.get_token()

    def logout(self, token):
        if token in self._sessions:
            self._sessions[token].end()
            del self._sessions[token]

    def get_account(self, token):
        session = self._sessions.get(token)
        if session is None or session.is_expired():
            self._sessions.pop(token, None)
            raise IntegrationError("please log in first", 401)
        session.extend()
        return session.get_account()

    def require_admin(self, token):
        account = self.get_account(token)
        if not account.is_admin():
            raise IntegrationError("only administrators can manage users", 403)
        return account

    # ---------- own account ----------
    def update_profile(self, token, region_name, street="", house_number=""):
        account = self.get_account(token)
        if not (region_name or "").strip():
            raise IntegrationError("please choose your city", 400)
        street, house_number = self._addresses.check_address(region_name.strip().title(), street, house_number)
        account.set_region_name(region_name)
        account.set_address(street, house_number)
        self._accounts.update(account)
        return account

    def change_password(self, token, old_password, new_password):
        account = self.get_account(token)
        if not account.check_password(old_password):
            raise IntegrationError("the current password is wrong", 400)
        account.set_password(new_password)
        self._accounts.update(account)

    def delete_account(self, token):
        # "delete my data": the account is removed and the scans are no longer linked to the person
        self._remove_user(self.get_account(token).get_user_id())

    # ---------- administration (admin role) ----------
    def list_users(self, token):
        self.require_admin(token)
        return [account.to_dict() for account in self._accounts.find_all()]

    def create_user(self, token, username, password, role, region_name):
        # municipality and admin accounts can only be created here
        self.require_admin(token)
        return self.register(username, password, role, region_name)

    def change_role(self, token, user_id, role):
        admin = self.require_admin(token)
        if admin.get_user_id() == user_id:
            raise IntegrationError("you cannot change your own role", 400)
        account = self._accounts.find_by_id(user_id)
        if account is None:
            raise IntegrationError("user not found", 404)
        account.set_role(role)
        self._accounts.update(account)
        self._end_sessions(user_id)          # the user logs in again with the new role
        return account

    def delete_user(self, token, user_id):
        admin = self.require_admin(token)
        if admin.get_user_id() == user_id:
            raise IntegrationError("you cannot delete your own account here", 400)
        if self._accounts.find_by_id(user_id) is None:
            raise IntegrationError("user not found", 404)
        self._remove_user(user_id)

    def get_user_count(self):
        return self._accounts.count()

    def _remove_user(self, user_id):
        self._scans.anonymize_user(user_id)
        self._accounts.delete(user_id)
        self._end_sessions(user_id)

    def _end_sessions(self, user_id):
        for key in [k for k, s in self._sessions.items() if s.get_account().get_user_id() == user_id]:
            del self._sessions[key]
