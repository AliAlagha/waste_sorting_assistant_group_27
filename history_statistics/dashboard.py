from datetime import datetime, timedelta

from .chart_builder import ChartBuilder
from .errors import StatisticsError
from .statistics_service import StatisticsService

DATE_FILTERS = [7, 30, 90, 365]


class Dashboard:
    # municipality dashboard: filters -> data from the database -> numbers and charts

    def __init__(self, repository, region_filter="All", date_filter=30):
        self._repository = repository
        self._service = StatisticsService()
        self._charts = ChartBuilder()
        self._region_filter = region_filter
        self._date_filter = date_filter

    # getters and setters

    def get_region_filter(self):
        return self._region_filter

    def set_region_filter(self, region_filter):
        self._region_filter = region_filter or "All"

    def get_date_filter(self):
        return self._date_filter

    def set_date_filter(self, days):
        try:
            days = int(days)
        except (TypeError, ValueError):
            raise StatisticsError("date filter must be a number of days")
        if days <= 0:
            raise StatisticsError("date filter must be more than 0 days")
        self._date_filter = days

    def get_regions(self):
        return ["All"] + self._repository.get_regions()

    # methods

    def filter_data(self):
        records = self._repository.find(self._region_filter, self._date_filter)
        self._service.load_records(records)
        return self._service.get_dataframe()

    def get_statistics(self):
        statistics = self._service.get_summary(self.filter_data())
        statistics["region_filter"] = self._region_filter
        statistics["date_filter"] = self._date_filter
        statistics["previous"] = self.get_previous_period()
        return statistics

    def get_previous_period(self):
        # the same number of days just before the selected period, to show if things got better
        end = datetime.now() - timedelta(days=self._date_filter)
        records = self._repository.find(self._region_filter, start=end - timedelta(days=self._date_filter), end=end)
        service = StatisticsService()
        service.load_records(records)
        df = service.get_dataframe()
        return {"scans": int(len(df)), "recycling_rate": service.get_recycle_rate(df)}

    def show_charts(self):
        statistics = self.get_statistics()
        statistics["charts"] = {
            "composition": self._charts.composition_chart(statistics["waste_composition"]),
            "trend": self._charts.recycling_trend_chart(statistics["recycling_rate_by_week"]),
            "common_items": self._charts.common_items_chart(statistics["most_common_items"]),
            "regions": self._charts.region_chart(statistics["composition_by_region"]),
        }
        return statistics

    def get_recent_scans(self, n=20):
        return [record.to_dict() for record in self._service.get_records()[:n]]

    def export_csv(self, path=None):
        df = self.filter_data()
        df = df.drop(columns=["scan_id"])
        if path is None:
            return df.to_csv(index=False)
        df.to_csv(path, index=False)
        return path
