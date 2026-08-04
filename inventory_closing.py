"""Daily closing balance ledger (dbo.InventoryDailyClosing) recalculation.

Users often enter inbound/outbound documents out of date order (a backdated
document can be saved after later-dated ones already exist). A naive
"today's row = yesterday's row + today's movement" approach breaks under
that pattern, since a backdated document changes every later day's running
balance. `recalculate()` sidesteps this entirely by always doing a full
rebuild of one product's whole history in date order — so the order
documents were entered in never matters, only their dates.
"""
import db


def recalculate(product_id):
    """Rebuild dbo.InventoryDailyClosing for one product — one row per date
    that actually has inbound/outbound movement (no carried-forward rows on
    no-movement days) — and sync Product.StockBalance to the resulting
    current balance.

    Uses plain db.query()/db.execute() (no transaction of its own) so it
    composes into whatever transaction the caller already has open.
    """
    inbound_rows = db.query("""
        SELECT h.InboundDate AS d, SUM(dt.Quantity) AS qty
        FROM dbo.InboundHeader h
        JOIN dbo.InboundDetail dt ON dt.InboundId = h.InboundId
        WHERE dt.ProductId = %s
        GROUP BY h.InboundDate
    """, (product_id,))
    outbound_rows = db.query("""
        SELECT h.OutboundDate AS d, SUM(dt.Quantity) AS qty
        FROM dbo.OutboundHeader h
        JOIN dbo.OutboundDetail dt ON dt.OutboundId = h.OutboundId
        WHERE dt.ProductId = %s
        GROUP BY h.OutboundDate
    """, (product_id,))

    inbound_map = {r["d"]: float(r["qty"]) for r in inbound_rows}
    outbound_map = {r["d"]: float(r["qty"]) for r in outbound_rows}

    db.execute("DELETE FROM dbo.InventoryDailyClosing WHERE ProductId = %s", (product_id,))

    all_dates = sorted(set(inbound_map) | set(outbound_map))
    if not all_dates:
        # recalculate() is only ever called for a product that a save/delete
        # just touched, so an empty result here means "its last remaining
        # transaction was just removed" — zero is the honest current
        # balance, not whatever the stale pre-deletion value was.
        db.execute("UPDATE dbo.Product SET StockBalance = 0 WHERE ProductId = %s", (product_id,))
        return

    opening = 0.0
    closing = opening
    for d in all_dates:
        in_qty = inbound_map.get(d, 0.0)
        out_qty = outbound_map.get(d, 0.0)
        closing = opening + in_qty - out_qty
        db.execute(
            "INSERT INTO dbo.InventoryDailyClosing "
            "(ClosingDate, ProductId, OpeningQuantity, InboundQuantity, OutboundQuantity, ClosingQuantity) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (d.isoformat(), product_id, opening, in_qty, out_qty, closing),
        )
        opening = closing

    db.execute("UPDATE dbo.Product SET StockBalance = %s WHERE ProductId = %s", (closing, product_id))
