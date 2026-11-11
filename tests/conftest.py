import pytest

from helpers import FakeEdg, FakeOpenAI, make_classification
from integration.api_gateway import ApiGateway
from integration.database import Database
from integration.sustainability_coach import SustainabilityCoach
from recommendations.edg_calendar import EdgCalendar


@pytest.fixture
def database():
    # the app uses MySQL; the tests use a throwaway in-memory database (nothing is written to disk)
    database = Database("sqlite://")
    database.create_tables()
    return database


@pytest.fixture
def make_gateway(database):
    # the whole app with a fake model, fake OpenAI and fake EDG website, plus one user of every role
    def _make(scores=None, coach=None):
        gateway = ApiGateway(database, make_classification(scores), coach=coach or SustainabilityCoach(client=FakeOpenAI()))
        gateway.setup()
        gateway.set_calendar(EdgCalendar(session=FakeEdg()))
        accounts = gateway.get_accounts()
        accounts.register("anna", "anna123", "citizen", "Dortmund")
        accounts.register("city", "city123", "municipality", "Dortmund")
        accounts.register("root", "root123", "admin", "Dortmund")
        return gateway
    return _make


@pytest.fixture
def gateway(make_gateway):
    return make_gateway()
