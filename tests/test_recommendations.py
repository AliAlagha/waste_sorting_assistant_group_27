# Recycling recommendations: local rules, preparation tips, collection days from EDG
from datetime import date

import pytest

from helpers import BrokenEdg, FakeEdg
from integration.classified_item import ClassifiedItem
from recommendations.edg_calendar import EdgCalendar
from recommendations.errors import RecommendationError
from recommendations.recommendation_service import RecommendationService
from recommendations.recycling_rule import RecyclingRule


@pytest.fixture
def service():
    service = RecommendationService("Dortmund")
    service.load_rules()
    return service


def test_item_gets_bin_and_tip(service):
    recommendation = service.recommend(ClassifiedItem("plastic", 0.9))
    assert recommendation.get_bin_name() == "Yellow bin"
    assert recommendation.get_rule().get_tip() == "Empty it, no need to wash it"


def test_uncertain_or_unknown_item_goes_to_grey_bin(service):
    assert service.recommend(ClassifiedItem("plastic", 0.3)).get_bin_name() == "Grey bin"
    assert service.recommend(ClassifiedItem("pizza box", 0.95)).get_bin_name() == "Grey bin"


def test_rule_needs_a_valid_category():
    with pytest.raises(RecommendationError):
        RecyclingRule("pizza box", "Burnable", "Grey bin")


def test_address_gives_real_collection_days(service):
    service.set_address("Sonnenstraße", "96", EdgCalendar(session=FakeEdg()))
    schedule = service.get_schedule()
    assert (schedule.get_pickup_day("Grey bin"), schedule.get_rhythm_text("Grey bin")) == ("Tuesday", "every week")
    assert schedule.get_pickup_day("Yellow bin") == "Friday"
    # the holiday shift from EDG is kept (Saturday 5 Dec instead of Friday 4 Dec)
    assert schedule.get_next_pickup("Yellow bin", date(2026, 11, 21)) == date(2026, 12, 5)


def test_unknown_address_is_an_error():
    with pytest.raises(RecommendationError, match="EDG knows: 94, 96, 96 a"):
        EdgCalendar(session=FakeEdg()).get_events("Sonnenstraße", "11")


def test_edg_down_is_an_error(service):
    service.set_calendar(EdgCalendar(session=BrokenEdg()))
    with pytest.raises(RecommendationError):
        service.recommend(ClassifiedItem("plastic", 0.9), "Sonnenstraße", "96")
