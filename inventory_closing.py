"""Daily closing balance ledger (dbo.InventoryDailyClosing) recalculation.

Users often enter inbound/outbound documents out of date order (a backdated
document can be saved after later-dated ones already exist). A naive
"today's row = yesterday's row + today's movement" approach breaks under
that pattern, since a backdated document changes every later day's running
balance. `recalculate()` sidesteps this entirely by always doing a full
rebuild of one (product, warehouse) pair's whole history in date order — so
the order documents were entered in never matters, only their dates.

Stock is tracked per warehouse (`dbo.ProductWarehouseStock`);
`Product.StockBalance` is a rollup (sum across all warehouses) kept in sync
whenever any of that product's warehouse pairs is recomputed.
"""
import db


def recalculate(product_id, warehouse_id):
    """Rebuild dbo.InventoryDailyClosing for one (product, warehouse) pair —
    one row per date that actually has inbound/outbound movement in that
    warehouse — sync dbo.ProductWarehouseStock for the pair, then roll
    Product.StockBalance up to the sum across all of that product's
    warehouses.

    Uses plain db.query()/db.execute() (no transaction of its own) so it
    composes into whatever transaction the caller already has open.
    """
    inbound_rows = db.query("""
        SELECT h.InboundDate AS d, SUM(dt.Quantity) AS qty
        FROM dbo.InboundHeader h
        JOIN dbo.InboundDetail dt ON dt.InboundId = h.InboundId
        WHERE dt.ProductId = %s AND h.WarehouseId = %s
        GROUP BY h.InboundDate
    """, (product_id, warehouse_id))
    # Only APPROVED outbound docs affect stock — a Pending/Rejected one
    # is excluded here, which is also how approve/reject/edit-resets-to-
    # Pending all "just work" via the same recalculate() call: whichever
    # status a doc is in, this filter alone decides whether it counts.
    outbound_rows = db.query("""
        SELECT h.OutboundDate AS d, SUM(dt.Quantity) AS qty
        FROM dbo.OutboundHeader h
        JOIN dbo.OutboundDetail dt ON dt.OutboundId = h.OutboundId
        WHERE dt.ProductId = %s AND h.WarehouseId = %s AND h.Status = 'APPROVED'
        GROUP BY h.OutboundDate
    """, (product_id, warehouse_id))

    inbound_map = {r["d"]: float(r["qty"]) for r in inbound_rows}
    outbound_map = {r["d"]: float(r["qty"]) for r in outbound_rows}

    db.execute(
        "DELETE FROM dbo.InventoryDailyClosing WHERE ProductId = %s AND WarehouseId = %s",
        (product_id, warehouse_id),
    )

    all_dates = sorted(set(inbound_map) | set(outbound_map))

    if not all_dates:
        # No movement left for this pair (its last transaction was just
        # removed, or moved to a different warehouse) — drop the row
        # entirely rather than leaving a stale zero-balance one. A
        # lingering ProductWarehouseStock row would otherwise block
        # deleting the Product later (FK_ProductWarehouseStock_Product)
        # even though there's no real history left to justify keeping it.
        db.execute(
            "DELETE FROM dbo.ProductWarehouseStock WHERE ProductId = %s AND WarehouseId = %s",
            (product_id, warehouse_id),
        )
        _rollup_product_stock(product_id)
        return

    closing = 0.0
    for d in all_dates:
        in_qty = inbound_map.get(d, 0.0)
        out_qty = outbound_map.get(d, 0.0)
        opening = closing
        closing = opening + in_qty - out_qty
        db.execute(
            "INSERT INTO dbo.InventoryDailyClosing "
            "(ClosingDate, ProductId, WarehouseId, OpeningQuantity, InboundQuantity, OutboundQuantity, ClosingQuantity) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (d.isoformat(), product_id, warehouse_id, opening, in_qty, out_qty, closing),
        )

    _upsert_warehouse_stock(product_id, warehouse_id, closing)
    _rollup_product_stock(product_id)


def _upsert_warehouse_stock(product_id, warehouse_id, balance):
    existing = db.query_one(
        "SELECT 1 AS x FROM dbo.ProductWarehouseStock WHERE ProductId = %s AND WarehouseId = %s",
        (product_id, warehouse_id),
    )
    if existing:
        db.execute(
            "UPDATE dbo.ProductWarehouseStock SET StockBalance = %s WHERE ProductId = %s AND WarehouseId = %s",
            (balance, product_id, warehouse_id),
        )
    else:
        db.execute(
            "INSERT INTO dbo.ProductWarehouseStock (ProductId, WarehouseId, StockBalance) VALUES (%s, %s, %s)",
            (product_id, warehouse_id, balance),
        )


def _rollup_product_stock(product_id):
    total = db.query_one(
        "SELECT ISNULL(SUM(StockBalance), 0) AS total FROM dbo.ProductWarehouseStock WHERE ProductId = %s",
        (product_id,),
    )["total"]
    db.execute("UPDATE dbo.Product SET StockBalance = %s WHERE ProductId = %s", (total, product_id))
