from datetime import datetime, timedelta

import pandas as pd
from sqlalchemy import select

from .database import request_log


class SystemMonitor:
    # numbers about the API itself, read from the table request_log (NFR: log every request)

    def __init__(self, database):
        self._database = database

    def get_dataframe(self, hours=24):
        query = select(request_log).where(request_log.c.created_at >= datetime.now() - timedelta(hours=hours))
        with self._database.get_engine().connect() as connection:
            rows = connection.execute(query).mappings().all()
        return pd.DataFrame([dict(row) for row in rows],
                            columns=["log_id", "method", "endpoint", "status_code", "duration_ms", "created_at"])

    def get_stats(self, hours=24):
        df = self.get_dataframe(hours)
        if len(df) == 0:
            return {"hours": hours, "requests": 0, "endpoints": [], "recent_errors": []}
        endpoints = (df.groupby(["method", "endpoint"])["duration_ms"].agg(["count", "mean", "max"])
                     .sort_values("count", ascending=False).head(10).reset_index())
        errors = df[df["status_code"] >= 500].sort_values("created_at", ascending=False).head(5)
        return {
            "hours": hours,
            "requests": int(len(df)),
            "average_ms": round(float(df["duration_ms"].mean()), 1),
            "p95_ms": round(float(df["duration_ms"].quantile(0.95)), 1),
            "client_errors": int(((df["status_code"] >= 400) & (df["status_code"] < 500)).sum()),
            "server_errors": int((df["status_code"] >= 500).sum()),
            "error_rate": round(float((df["status_code"] >= 500).mean() * 100), 2),
            "endpoints": [{"method": r["method"], "endpoint": r["endpoint"], "count": int(r["count"]),
                           "average_ms": round(float(r["mean"]), 1), "max_ms": round(float(r["max"]), 1)}
                          for _, r in endpoints.iterrows()],
            "recent_errors": [{"time": str(r["created_at"])[:19], "method": r["method"], "endpoint": r["endpoint"],
                               "status_code": int(r["status_code"])} for _, r in errors.iterrows()],
        }
