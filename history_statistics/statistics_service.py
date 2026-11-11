import pandas as pd

COLUMNS = ["scan_id", "region_name", "category", "item_name", "bin_name", "confidence", "status", "scan_date"]


class StatisticsService:
    # turns a list of ScanRecords into numbers for the dashboard (with pandas)

    def __init__(self):
        self._records = []

    def load_records(self, records):
        self._records = list(records)

    # getters and setters

    def get_records(self):
        return self._records

    # methods

    # pandas makes the counting much easier than loops
    def get_dataframe(self):
        df = pd.DataFrame([r.to_dict() for r in self._records], columns=COLUMNS)
        df["scan_date"] = pd.to_datetime(df["scan_date"])
        return df

    def get_totals(self, df):
        return {category: int(amount) for category, amount in df["category"].value_counts().items()}

    def get_recycle_rate(self, df):
        if len(df) == 0:
            return 0
        recyclable = len(df[df["category"] == "Recyclable"])
        return round(recyclable / len(df) * 100, 1)

    def get_most_common_items(self, df, n=5):
        return {item: int(amount) for item, amount in df["item_name"].value_counts().head(n).items()}

    def get_recycle_rate_by_week(self, df):
        # recycling rate (%) for every week, used for the trend chart
        if len(df) == 0:
            return {}
        weeks = df.set_index("scan_date").groupby(pd.Grouper(freq="W"))["category"]
        rates = weeks.apply(lambda c: round((c == "Recyclable").mean() * 100, 1) if len(c) else None).dropna()
        return {str(day.date()): float(rate) for day, rate in rates.items()}

    def get_composition_by_region(self, df):
        # {"Dortmund": {"Recyclable": 10, ...}, ...}
        if len(df) == 0:
            return {}
        table = pd.crosstab(df["region_name"], df["category"])
        return {region: {c: int(v) for c, v in row.items()} for region, row in table.iterrows()}

    def get_summary(self, df):
        return {
            "scans": int(len(df)),
            "waste_composition": self.get_totals(df),
            "recycling_rate": self.get_recycle_rate(df),
            "most_common_items": self.get_most_common_items(df),
            "recycling_rate_by_week": self.get_recycle_rate_by_week(df),
            "composition_by_region": self.get_composition_by_region(df),
        }
