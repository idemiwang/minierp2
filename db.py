import pytds
from flask import g
from config import Config


def get_connection():
    if "db_conn" not in g:
        g.db_conn = pytds.connect(
            server=Config.DB_SERVER,
            port=Config.DB_PORT,
            user=Config.DB_USER,
            password=Config.DB_PASSWORD,
            database=Config.DB_NAME,
            timeout=30,
            login_timeout=30,
            autocommit=True,
        )
    return g.db_conn


def close_connection(_exc=None):
    conn = g.pop("db_conn", None)
    if conn is not None:
        conn.close()


def query(sql, params=None):
    """SELECT helper — returns a list of dicts."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(sql, params or ())
    cols = [d[0] for d in cur.description] if cur.description else []
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def query_one(sql, params=None):
    rows = query(sql, params)
    return rows[0] if rows else None


def execute(sql, params=None):
    """INSERT/UPDATE/DELETE helper. Runs on the request's connection —
    autocommit unless inside a `transaction()` block."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(sql, params or ())
    return cur


class transaction:
    """Context manager: groups statements into one transaction. Commits on
    clean exit, rolls back on any exception. Nested use is not supported —
    keep transaction blocks to a single request-handler operation."""

    def __enter__(self):
        self.conn = get_connection()
        self.conn.autocommit = False
        return self.conn

    def __exit__(self, exc_type, exc, _tb):
        try:
            if exc_type is None:
                self.conn.commit()
            else:
                self.conn.rollback()
        finally:
            self.conn.autocommit = True
        return False
