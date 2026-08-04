"""
Applies sql/*.sql migration files against the configured database in order,
tracking which have already run in dbo.__SchemaMigrations so re-running this
script is idempotent. Files use a "GO" on its own line as a batch separator
(the SSMS/sqlcmd convention) — required because CREATE VIEW/PROC/TRIGGER
must be the only statement in their batch.

Usage:
    set -a; source .env; set +a
    python3 scripts/apply_migrations.py
"""
import os
import pytds
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env"))

SQL_DIR = os.path.join(os.path.dirname(__file__), "..", "sql")


def connect():
    return pytds.connect(
        server=os.environ["DB_SERVER"],
        port=int(os.environ.get("DB_PORT", 1433)),
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        database=os.environ["DB_NAME"],
        timeout=30,
        login_timeout=30,
        autocommit=True,
    )


def ensure_tracking_table(cur):
    cur.execute("""
        IF OBJECT_ID('dbo.__SchemaMigrations', 'U') IS NULL
        CREATE TABLE dbo.__SchemaMigrations (
            Filename  NVARCHAR(255) NOT NULL PRIMARY KEY,
            AppliedAt DATETIME2     NOT NULL DEFAULT SYSUTCDATETIME()
        )
    """)


def applied_files(cur):
    cur.execute("SELECT Filename FROM dbo.__SchemaMigrations")
    return {row[0] for row in cur.fetchall()}


def split_batches(sql_text):
    batches, current = [], []
    for line in sql_text.splitlines():
        if line.strip().upper() == "GO":
            if current:
                batches.append("\n".join(current))
                current = []
        else:
            current.append(line)
    if current:
        batches.append("\n".join(current))
    return [b.strip() for b in batches if b.strip()]


def main():
    conn = connect()
    cur = conn.cursor()
    ensure_tracking_table(cur)
    done = applied_files(cur)

    for fname in sorted(f for f in os.listdir(SQL_DIR) if f.endswith(".sql")):
        if fname in done:
            print(f"skip (already applied): {fname}")
            continue
        with open(os.path.join(SQL_DIR, fname), encoding="utf-8") as f:
            text = f.read()
        print(f"applying: {fname}")
        for batch in split_batches(text):
            cur.execute(batch)
        cur.execute(
            "INSERT INTO dbo.__SchemaMigrations (Filename) VALUES (%s)",
            (fname,),
        )
        print(f"  done: {fname}")

    conn.close()


if __name__ == "__main__":
    main()
