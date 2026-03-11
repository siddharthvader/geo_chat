from __future__ import annotations

from contextlib import contextmanager

from psycopg import Connection
from psycopg.rows import dict_row

from app.core.config import get_settings


def vector_literal(values: list[float]) -> str:
    return "[" + ",".join(f"{v:.8f}" for v in values) + "]"


@contextmanager
def get_conn() -> Connection:
    conn = Connection.connect(get_settings().database_url, row_factory=dict_row)
    try:
        yield conn
    finally:
        conn.close()
