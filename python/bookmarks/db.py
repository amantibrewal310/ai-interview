import os
import sqlite3
from contextlib import contextmanager

DB_PATH = os.environ.get("DB_PATH", "bookmarks.db")


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def connect():
    """Yield a connection, commit on success, roll back on error, always close."""
    conn = get_conn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@contextmanager
def transaction():
    """Like connect(), but takes the write lock up front so check-then-write is safe."""
    conn = get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    with open(os.path.join(os.path.dirname(__file__), "schema.sql")) as f:
        schema = f.read()
    with connect() as conn:
        conn.executescript(schema)
        # CREATE TABLE IF NOT EXISTS does not add columns to an existing table,
        # so databases created before soft delete need the column added once.
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(bookmarks)")}
        if "is_deleted" not in columns:
            conn.execute(
                "ALTER TABLE bookmarks ADD COLUMN is_deleted INTEGER NOT NULL DEFAULT 0 "
                "CHECK (is_deleted IN (0, 1))"
            )
