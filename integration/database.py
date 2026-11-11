import os
from datetime import datetime

from sqlalchemy import Column, DateTime, Float, Integer, MetaData, String, Table, create_engine, func, insert, select
from sqlalchemy.engine import make_url

from .errors import IntegrationError

metadata = MetaData()

# all tables of the app (see README for the ER overview)
users = Table(
    "users", metadata,
    Column("user_id", Integer, primary_key=True, autoincrement=True),
    Column("username", String(50), nullable=False, unique=True),
    Column("password_hash", String(255), nullable=False),
    Column("role", String(20), nullable=False),
    Column("region_name", String(100), nullable=False),
    Column("street", String(100), nullable=False, default=""),
    Column("house_number", String(20), nullable=False, default=""),
    Column("created_at", DateTime, nullable=False),
)

scan_records = Table(
    "scan_records", metadata,
    Column("scan_id", Integer, primary_key=True, autoincrement=True),
    Column("user_id", Integer, nullable=True),
    Column("region_name", String(100), nullable=False),
    Column("category", String(20), nullable=False),
    Column("item_name", String(100), nullable=False),
    Column("bin_name", String(100), nullable=False, default=""),
    Column("confidence", Float, nullable=True),
    Column("status", String(20), nullable=False, default="ok"),
    Column("scan_date", DateTime, nullable=False),
)

request_log = Table(
    "request_log", metadata,
    Column("log_id", Integer, primary_key=True, autoincrement=True),
    Column("method", String(10), nullable=False),
    Column("endpoint", String(200), nullable=False),
    Column("status_code", Integer, nullable=False),
    Column("duration_ms", Float, nullable=False),
    Column("created_at", DateTime, nullable=False),
)

class Database:
    # one connection pool to the MySQL database for the whole app

    def __init__(self, url=None):
        # the MySQL server, e.g. mysql+pymysql://user:password@db:3306/waste_sorting (set in docker-compose.yml)
        self._url = url or os.environ.get("DATABASE_URL", "")
        if not self._url:
            raise IntegrationError("DATABASE_URL is not set", 500)
        self._engine = create_engine(self._url, pool_pre_ping=True)

    def get_engine(self):
        return self._engine

    def create_tables(self):
        metadata.create_all(self._engine)

    def describe(self):
        # where the data lives and how many rows every table has (shown to the admin)
        url = make_url(self._url)
        location = "{}:{}/{}".format(url.host, url.port, url.database)
        with self._engine.connect() as connection:
            tables = {table.name: connection.execute(select(func.count()).select_from(table)).scalar()
                      for table in metadata.sorted_tables}
        return {"engine": url.get_backend_name(), "location": location, "tables": tables}

    def is_available(self):
        try:
            with self._engine.connect() as connection:
                connection.execute(select(1))
            return True
        except Exception:
            return False

    def log_request(self, method, endpoint, status_code, duration_ms):
        with self._engine.begin() as connection:
            connection.execute(insert(request_log).values(
                method=method, endpoint=endpoint[:200], status_code=status_code,
                duration_ms=round(duration_ms, 1), created_at=datetime.now()))
