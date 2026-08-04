"""
Read-only schema introspection for the kimtae (mini ERP) database.

Only queries system catalog views (sys.*, INFORMATION_SCHEMA.*) — no DML, no DCL.
Credentials are supplied via environment variables (see .env.example), never
hardcoded, so this script is safe to keep in version control.

Usage:
    set -a; source .env; set +a
    python3 scripts/introspect_schema.py
"""
import os
import json
import pytds
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env"))

conn = pytds.connect(
    server=os.environ["DB_SERVER"],
    port=int(os.environ.get("DB_PORT", 1433)),
    user=os.environ["DB_USER"],
    password=os.environ["DB_PASSWORD"],
    database=os.environ["DB_NAME"],
    timeout=30,
    login_timeout=30,
    autocommit=True,
)
cur = conn.cursor()


def q(sql):
    cur.execute(sql)
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


result = {}

result["tables"] = q("""
    SELECT s.name AS schema_name, t.name AS table_name, t.object_id
    FROM sys.tables t
    JOIN sys.schemas s ON t.schema_id = s.schema_id
    ORDER BY s.name, t.name
""")

result["columns"] = q("""
    SELECT s.name AS schema_name, t.name AS table_name, c.column_id,
           c.name AS column_name, ty.name AS data_type,
           c.max_length, c.precision, c.scale,
           c.is_nullable, c.is_identity
    FROM sys.columns c
    JOIN sys.tables t ON c.object_id = t.object_id
    JOIN sys.schemas s ON t.schema_id = s.schema_id
    JOIN sys.types ty ON c.user_type_id = ty.user_type_id
    ORDER BY s.name, t.name, c.column_id
""")

result["primary_keys"] = q("""
    SELECT s.name AS schema_name, t.name AS table_name,
           c.name AS column_name, ic.key_ordinal
    FROM sys.key_constraints kc
    JOIN sys.tables t ON kc.parent_object_id = t.object_id
    JOIN sys.schemas s ON t.schema_id = s.schema_id
    JOIN sys.index_columns ic ON ic.object_id = t.object_id AND ic.index_id = kc.unique_index_id
    JOIN sys.columns c ON c.object_id = t.object_id AND c.column_id = ic.column_id
    WHERE kc.type = 'PK'
    ORDER BY s.name, t.name, ic.key_ordinal
""")

result["foreign_keys"] = q("""
    SELECT
        fk.name AS fk_name, fk.is_disabled, fk.is_not_trusted,
        sp.name AS parent_schema, tp.name AS parent_table, cp.name AS parent_column,
        sr.name AS ref_schema, tr.name AS ref_table, cr.name AS ref_column
    FROM sys.foreign_keys fk
    JOIN sys.foreign_key_columns fkc ON fk.object_id = fkc.constraint_object_id
    JOIN sys.tables tp ON fkc.parent_object_id = tp.object_id
    JOIN sys.schemas sp ON tp.schema_id = sp.schema_id
    JOIN sys.columns cp ON cp.object_id = tp.object_id AND cp.column_id = fkc.parent_column_id
    JOIN sys.tables tr ON fkc.referenced_object_id = tr.object_id
    JOIN sys.schemas sr ON tr.schema_id = sr.schema_id
    JOIN sys.columns cr ON cr.object_id = tr.object_id AND cr.column_id = fkc.referenced_column_id
    ORDER BY parent_table, fk_name
""")

result["views"] = q("""
    SELECT o.name AS view_name, m.definition
    FROM sys.sql_modules m
    JOIN sys.objects o ON m.object_id = o.object_id
    WHERE o.type = 'V'
""")

result["row_counts"] = q("""
    SELECT s.name AS schema_name, t.name AS table_name, p.rows AS row_count
    FROM sys.tables t
    JOIN sys.schemas s ON t.schema_id = s.schema_id
    JOIN sys.partitions p ON t.object_id = p.object_id AND p.index_id IN (0, 1)
    ORDER BY s.name, t.name
""")

out_path = os.path.join(os.path.dirname(__file__), "..", "schema_dump.json")
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(result, f, ensure_ascii=False, indent=2, default=str)

print(f"Tables: {len(result['tables'])}, Columns: {len(result['columns'])}, "
      f"PK columns: {len(result['primary_keys'])}, FKs: {len(result['foreign_keys'])}, "
      f"Views: {len(result['views'])}")
conn.close()
