# History and statistics: saving scans, filters, pandas totals, charts, CSV export
from datetime import datetime, timedelta

import pytest

from history_statistics.dashboard import Dashboard
from history_statistics.errors import StatisticsError
from history_statistics.scan_record import ScanRecord
from history_statistics.scan_repository import ScanRepository


@pytest.fixture
def repository(database):
    repository = ScanRepository(database)
    now = datetime.now()
    for region, category, item, days_ago in [("Dortmund", "Recyclable", "plastic", 1), ("Dortmund", "Compostable", "biological", 2),
                                              ("Bochum", "Landfill", "trash", 3), ("Bochum", "Recyclable", "metal", 4),
                                              ("Essen", "Recyclable", "plastic", 40)]:
        repository.save(ScanRecord(None, region, category, item, now - timedelta(days=days_ago)))
    return repository


def test_scans_are_saved_and_filtered(repository):
    assert len(repository.find()) == 5
    assert len(repository.find("Bochum")) == 2
    assert len(repository.find(days=30)) == 4
    assert repository.get_regions() == ["Bochum", "Dortmund", "Essen"]


def test_dashboard_statistics(repository):
    dashboard = Dashboard(repository)
    statistics = dashboard.get_statistics()                   # last 30 days, all regions
    assert statistics["scans"] == 4 and statistics["recycling_rate"] == 50.0
    assert statistics["waste_composition"] == {"Recyclable": 2, "Compostable": 1, "Landfill": 1}
    assert statistics["previous"] == {"scans": 1, "recycling_rate": 100.0}
    dashboard.set_region_filter("Dortmund")
    dashboard.set_date_filter(7)
    assert dashboard.get_statistics()["scans"] == 2


def test_wrong_date_filter_is_an_error(repository):
    with pytest.raises(StatisticsError):
        Dashboard(repository).set_date_filter(0)


def test_charts_and_csv_export(repository):
    dashboard = Dashboard(repository)
    assert all(chart.startswith("iVBOR") for chart in dashboard.show_charts()["charts"].values())   # PNG pictures
    csv = dashboard.export_csv().splitlines()
    assert csv[0].startswith("region_name,category,item_name") and len(csv) == 5


def test_deleted_user_scans_stay_anonymous(database):
    repository = ScanRepository(database)
    repository.save(ScanRecord(None, "Dortmund", "Recyclable", "paper", user_id=7))
    repository.anonymize_user(7)
    assert repository.find(user_id=7) == [] and repository.count() == 1
