# User interface and integration: one scan through all subsystems, accounts, roles, admin, address check, coach
import pytest

from helpers import FakeOpenAI, make_image
from integration.account import Account
from integration.errors import IntegrationError
from integration.sustainability_coach import SustainabilityCoach


@pytest.fixture
def accounts(gateway):
    return gateway.get_accounts()


def test_scan_goes_through_all_subsystems(gateway, accounts):
    token = accounts.login("anna", "anna123")
    result = gateway.scan(token, make_image())
    assert result["classification"]["item"] == "plastic"                 # AI classification
    assert result["recommendation"]["bin_name"] == "Yellow bin"          # recycling recommendations
    assert result["coach"]["text"] == "Rinse and recycle."              # OpenAI coach
    assert gateway.my_history(token)["scans"] == 1                       # history


def test_invalid_photo_returns_400(gateway, accounts):
    with pytest.raises(IntegrationError) as error:
        gateway.scan(accounts.login("anna", "anna123"), b"not a photo")
    assert error.value.status_code == 400


def test_partial_result_when_the_coach_fails(make_gateway):
    gateway = make_gateway(coach=SustainabilityCoach(client=FakeOpenAI(fail=True)))
    result = gateway.scan(gateway.get_accounts().login("anna", "anna123"), make_image())
    assert result["coach"] is None and result["recommendation"]["bin_name"] == "Yellow bin"
    assert result["warnings"] == ["the AI coach is not available right now"]


def test_login_and_password_hash(accounts):
    with pytest.raises(IntegrationError) as error:
        accounts.login("anna", "wrong")
    assert error.value.status_code == 401
    assert "anna123" not in Account("anna", "anna123", "citizen", "Dortmund").get_password_hash()


def test_pages_are_restricted_by_role(gateway, accounts):
    anna = accounts.login("anna", "anna123")
    for call in (lambda: gateway.dashboard(anna), lambda: accounts.list_users(anna)):
        with pytest.raises(IntegrationError) as error:
            call()
        assert error.value.status_code == 403
    assert gateway.dashboard(accounts.login("city", "city123"))["scans"] == 0


def test_admin_manages_users_and_roles(accounts):
    root = accounts.login("root", "root123")
    anna_id = [u["user_id"] for u in accounts.list_users(root) if u["username"] == "anna"][0]
    anna = accounts.login("anna", "anna123")
    accounts.change_role(root, anna_id, "municipality")
    with pytest.raises(IntegrationError):
        accounts.get_account(anna)                                         # logged out after the role change
    accounts.delete_user(root, anna_id)
    assert "anna" not in {u["username"] for u in accounts.list_users(root)}


def test_address_must_be_known_by_edg(gateway, accounts):
    anna = accounts.login("anna", "anna123")
    with pytest.raises(IntegrationError, match="EDG knows: 94, 96, 96 a"):
        accounts.update_profile(anna, "Dortmund", "Sonnenstraße", "11")
    accounts.update_profile(anna, "Dortmund", "Sonnenstraße", "96")
    assert accounts.get_account(anna).get_street() == "Sonnenstr."         # stored in EDG's spelling
    assert gateway.my_schedule(anna)["has_address"] is True


def test_coach_without_key_is_an_error():
    with pytest.raises(IntegrationError, match="OPENAI_API_KEY"):
        SustainabilityCoach(api_key="").explain("plastic", "Recyclable", "Yellow bin", "Dortmund")
