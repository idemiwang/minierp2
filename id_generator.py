"""System-generated IDs for entities that have no IDENTITY column.

Each `next_*_id()` reads existing IDs matching the entity's prefix and picks
the next free numeric suffix. Callers should generate the id and attempt the
insert inside the same transaction, retrying via `generate_with_retry` on a
collision (two saves racing for the same number) — acceptable for this
app's expected concurrency (single admin, small class project), not meant
to scale to high-concurrency writers.
"""
from datetime import date

import pytds

import db


def _next_numeric_suffix(existing_ids, prefix):
    max_n = 0
    for id_ in existing_ids:
        suffix = id_[len(prefix):]
        if suffix.isdigit():
            max_n = max(max_n, int(suffix))
    return max_n + 1


def next_product_id():
    rows = db.query("SELECT ProductId FROM dbo.Product WHERE ProductId LIKE %s", ("P%",))
    n = _next_numeric_suffix([r["ProductId"] for r in rows], "P")
    return f"P{n:04d}"


def next_employee_id():
    rows = db.query("SELECT EmployeeId FROM dbo.Employee WHERE EmployeeId LIKE %s", ("E%",))
    n = _next_numeric_suffix([r["EmployeeId"] for r in rows], "E")
    return f"E{n:04d}"


def next_inbound_id():
    prefix = f"IN{date.today().strftime('%Y%m%d')}"
    rows = db.query("SELECT InboundId FROM dbo.InboundHeader WHERE InboundId LIKE %s", (prefix + "%",))
    n = _next_numeric_suffix([r["InboundId"] for r in rows], prefix)
    return f"{prefix}{n:03d}"


def next_outbound_id():
    prefix = f"OUT{date.today().strftime('%Y%m%d')}"
    rows = db.query("SELECT OutboundId FROM dbo.OutboundHeader WHERE OutboundId LIKE %s", (prefix + "%",))
    n = _next_numeric_suffix([r["OutboundId"] for r in rows], prefix)
    return f"{prefix}{n:03d}"


def generate_with_retry(generate_fn, insert_fn, attempts=3):
    """Call generate_fn() then insert_fn(id); retry on a PK collision."""
    last_exc = None
    for _ in range(attempts):
        new_id = generate_fn()
        try:
            insert_fn(new_id)
            return new_id
        except pytds.tds_base.IntegrityError as exc:
            last_exc = exc
    raise last_exc
