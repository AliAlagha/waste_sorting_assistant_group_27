from datetime import datetime, timedelta

from sqlalchemy import insert, select, update
from sqlalchemy.exc import SQLAlchemyError

from integration.database import scan_records

from .errors import StatisticsError
from .scan_record import ScanRecord


class ScanRepository:
    # reads and writes the table scan_records

    def __init__(self, database):
        self._database = database

    def save(self, record):
        values = record.to_dict()
        del values["scan_id"]
        values["user_id"] = record.get_user_id()
        try:
            with self._database.get_engine().begin() as connection:
                result = connection.execute(insert(scan_records).values(**values))
        except SQLAlchemyError as error:
            raise StatisticsError("scan could not be saved: " + str(error.__class__.__name__))
        record.set_scan_id(result.inserted_primary_key[0])
        return record

    def find(self, region_name="All", days=None, user_id=None, limit=None, start=None, end=None):
        # days = the last x days; start / end = any time range (used to compare with the previous period)
        query = select(scan_records).order_by(scan_records.c.scan_date.desc())
        if region_name and region_name != "All":
            query = query.where(scan_records.c.region_name == region_name)
        if days:
            query = query.where(scan_records.c.scan_date >= datetime.now() - timedelta(days=days))
        if start is not None:
            query = query.where(scan_records.c.scan_date >= start)
        if end is not None:
            query = query.where(scan_records.c.scan_date < end)
        if user_id is not None:
            query = query.where(scan_records.c.user_id == user_id)
        if limit:
            query = query.limit(limit)
        try:
            with self._database.get_engine().connect() as connection:
                rows = connection.execute(query).mappings().all()
        except SQLAlchemyError as error:
            raise StatisticsError("scans could not be loaded: " + str(error.__class__.__name__))
        return [self._to_record(row) for row in rows]

    def get_regions(self):
        query = select(scan_records.c.region_name).distinct().order_by(scan_records.c.region_name)
        with self._database.get_engine().connect() as connection:
            return [row[0] for row in connection.execute(query)]

    def count(self):
        with self._database.get_engine().connect() as connection:
            return len(connection.execute(select(scan_records.c.scan_id)).all())

    def anonymize_user(self, user_id):
        # the statistics stay, but the scans are not linked to the person any more
        with self._database.get_engine().begin() as connection:
            connection.execute(update(scan_records).where(scan_records.c.user_id == user_id).values(user_id=None))

    def _to_record(self, row):
        return ScanRecord(row["scan_id"], row["region_name"], row["category"], row["item_name"],
                          row["scan_date"], row["bin_name"], row["confidence"], row["status"], row["user_id"])
