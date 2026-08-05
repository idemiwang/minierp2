# CLAUDE.md

Context for Claude Code (or any future assistant) working in this repo.

**Keep this file and `SKILL.md` up to date.** Whenever the schema, routes,
or conventions below change, update both files in the same change — that's
an explicit project convention here, not optional cleanup.

## What this repo is

`minierp2` is a small web-based ERP (Flask + SQL Server) covering: master
data (Product / Employee / Warehouse / DocType / Customer / Vendor),
transactional data (Inbound / Outbound documents with line items, each
tagged with a warehouse, a document type, and an optional vendor/customer),
per-warehouse inventory tracking, and report/query screens over union
views. See `SKILL.md` for the step-by-step pattern used to add a new
module.

## Database connection

```
server:   163.17.141.61
port:     8082
database: kimtae
```

Same server as the separate `minierp` repo (a read-only schema-audit
project against a *different* database, `biz00`) — don't confuse the two.
Credentials come from `.env` (`DB_SERVER`, `DB_PORT`, `DB_NAME`, `DB_USER`,
`DB_PASSWORD`; see `.env.example`), never hardcoded. `.env` is git-ignored.

Driver: `pytds` (pure-Python TDS client, package name `python-tds`).

## This database is read-write

Unlike `minierp`/`biz00`, the app performs real INSERT/UPDATE/DELETE against
`kimtae` as its core function. The constraint here is narrower: **no ad-hoc
destructive DDL** run outside a reviewed file in `sql/`. Schema changes go
through a numbered migration file (`sql/NNN_description.sql`, "GO" on its
own line as a batch separator) applied via `scripts/apply_migrations.py`,
which tracks what's already run in `dbo.__SchemaMigrations` so re-running
it is idempotent.

`kimtae` started completely empty (0 tables/views) — `sql/001_create_tables.sql`
and `sql/002_create_views.sql` created the whole schema (mirroring `biz00`'s
structure/FKs from `minierp/schema_dump.json`, since the assignment spec
matches it column-for-column). Re-run `scripts/introspect_schema.py` after
any manual schema change to refresh `schema_dump.json`.

### v_inoutheader / v_inoutdetail naming quirk

Both views are a literal `SELECT * FROM InboundX UNION ALL SELECT * FROM
OutboundX` (per the assignment spec). Since `InboundHeader`'s PK column is
named `InboundId` and `OutboundHeader`'s is `OutboundId`, the UNION matches
positionally and the view exposes **both** under the first query's column
name (`InboundId`) — an outbound-sourced row's transaction id shows up
under a column literally called `InboundId`. This is intentional fidelity
to the spec, not a bug. The app/templates treat that column as a generic
transaction id and never rely on its name to infer inbound-vs-outbound.

### InboundHeader / OutboundHeader are kept column-for-column symmetric

`sql/004_add_doctype_warehouse_partners.sql` added `WarehouseId, DocTypeId,
VendorId, CustomerId` to **both** headers — not just `VendorId` on
`InboundHeader` and `CustomerId` on `OutboundHeader`, even though each
table only ever populates one of that pair (`InboundHeader.CustomerId` and
`OutboundHeader.VendorId` are always `NULL`). This is deliberate: keeping
both tables the same shape means `v_inoutheader`'s literal `SELECT *
... UNION ALL SELECT * ...` above needed zero changes when this landed —
a mismatched column count/order between the two `SELECT *`s would have
broken the UNION. If you add another header-level column later, add it to
**both** tables the same way to preserve this.

That migration also **dropped and recreated** `InventoryDailyClosing`
(added `WarehouseId` to its PK) since that table is entirely derived by
`inventory_closing.recalculate()` — never hand-entered — so nothing was
lost; the app just needs `recalculate()` re-run once per existing
`(ProductId, WarehouseId)` pair to repopulate it (already done for the
data that existed at migration time).

## Running locally

```bash
cd minierp2
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
cp .env.example .env   # fill in DB_PASSWORD and generate APP_PASSWORD_HASH
./venv/bin/python3 scripts/apply_migrations.py   # first run only / after adding a migration
./venv/bin/python3 app.py                        # http://127.0.0.1:5050
```

Generate `APP_PASSWORD_HASH`:
```bash
./venv/bin/python3 -c "from werkzeug.security import generate_password_hash; print(generate_password_hash('your-password', method='pbkdf2:sha256'))"
```
(`method='pbkdf2:sha256'` matters — this machine's Python lacks
`hashlib.scrypt`, which is werkzeug's newer default and raises
`AttributeError` if omitted.)

## Login

Single-account session login (no user-management system, per project
scope) — username/password-hash come from `.env` (`APP_USERNAME`,
`APP_PASSWORD_HASH`), checked in `auth.py`. `app.before_request` blocks
every route except `/login` and static assets until `session["user"]` is
set.

## ID generation

None of the PKs are IDENTITY columns, so the app generates them
(`id_generator.py`):
- `ProductId` — `P0001`, `P0002`, … (next = max existing numeric suffix + 1)
- `EmployeeId` — `E0001`, `E0002`, … (same scheme)
- `InboundId` / `OutboundId` — `IN`/`OUT` + `YYYYMMDD` + 3-digit daily
  sequence (e.g. `IN20260804001`), sequence resets per day
- `WarehouseId` — `W0001`, `W0002`, … ; `DocTypeId` — `D0001`, … (8 seeded
  by the migration: `D0001`-`D0004` for 入庫, `D0005`-`D0008` for 出庫);
  `CustomerId` — `C0001`, … ; `VendorId` — `V0001`, … — all the same
  max-existing-suffix-plus-one scheme

`id_generator.generate_with_retry()` retries once on a PK collision (two
saves racing for the same number) — fine for this app's expected
concurrency (single admin), not built to scale beyond that.

## Delete-guard business rule

Product and Employee master rows **cannot be deleted once they have
related transaction detail rows** (`v_inoutdetail`/`v_inoutheader` filtered
by the key). The app pre-checks with a `COUNT(*)` and shows a friendly
flash message rather than a raw FK-violation error; the underlying FK
constraints (`FK_InboundDetail_Product`, `FK_OutboundHeader_Employee`,
etc.) are a defense-in-depth fallback the app also catches.

Same pattern for the four newer master types, each guarded against the
header table(s) that actually reference it: Warehouse and DocType block
if referenced by **either** `InboundHeader` or `OutboundHeader`; Vendor
blocks only against `InboundHeader.VendorId`; Customer only against
`OutboundHeader.CustomerId` (see `blueprints/warehouse.py`,
`doctype.py`, `vendor.py`, `customer.py`).

## Transactional save pattern (Inbound / Outbound)

Header + line-item saves happen inside `db.transaction()`: on update, all
existing detail rows for that document are deleted and the current grid
state is re-inserted — simplest correct approach for a small line grid,
avoids diffing added/changed/removed rows.

## Per-warehouse stock: dbo.ProductWarehouseStock and daily closing

Stock is tracked **per (Product, Warehouse) pair**, not globally per
product. `dbo.ProductWarehouseStock` holds each pair's current balance;
`Product.StockBalance` is a **rollup** — `SUM(ProductWarehouseStock.StockBalance)`
for that product across every warehouse — recomputed alongside, so the
Product list's single "庫存餘額" column still shows a meaningful total.

`inventory_closing.recalculate(product_id, warehouse_id)` is called for
every `(ProductId, WarehouseId)` pair touched by an inbound/outbound
create/edit/delete, **inside the same `db.transaction()` block** as the
header/detail save (so a closing-table failure rolls back the whole save).
Since `WarehouseId` lives on the **header** (one warehouse per document,
not per line), the affected set is `{(pid, wid) for pid in
affected_products for wid in affected_warehouses}`:
- create: `affected_warehouses = {new_warehouse_id}`
- delete: `affected_warehouses = {the header's WarehouseId}`
- edit: `affected_warehouses = {old_warehouse_id, new_warehouse_id}` — if
  a document is moved to a different warehouse, **both** the old and new
  warehouse's history for every touched product must be recomputed, since
  the movement disappears from one and appears in the other.

**Users often enter documents out of date order** (a backdated document
can be saved after later-dated ones already exist). `recalculate()`
handles this by never doing an incremental patch — it always fully
rebuilds one `(product, warehouse)` pair's whole daily-closing history in
date order:

1. Sum inbound/outbound quantities per date for that product **in that
   warehouse** (both sides, always — the closing balance depends on both
   regardless of which blueprint triggered the call).
2. Delete all existing `InventoryDailyClosing` rows for that pair.
3. Sort the distinct dates that actually have movement (ascending) and
   walk through *only those* — no row for a no-movement day. `opening =
   previous *recorded* day's closing` (0 on the first recorded day),
   `closing = opening + inbound - outbound`, one row per movement date.
   This is what makes entry order irrelevant — the rebuild always replays
   in date order regardless of the order documents were saved in.
4. Upsert `ProductWarehouseStock` for the pair to the last recorded day's
   `ClosingQuantity` — or **delete** that pair's row entirely if there
   were no dates at all (only happens right after a save/delete/warehouse-
   move removed that pair's *last* transaction). Deleting rather than
   zeroing matters here: a lingering zero-balance row still holds a live
   FK to `Product`, which would silently block deleting that product later
   even though no real history justifies keeping it.
5. Roll `Product.StockBalance` up to the sum across all of that product's
   `ProductWarehouseStock` rows.

**Behavior worth knowing (not a bug)**: since each pair's rebuild always
starts from an opening balance of 0 on its first-ever activity date, a
manually-typed `StockBalance` on the Product form only holds until that
product's *first* inbound/outbound is saved anywhere — after that,
`StockBalance` is fully derived from recorded movements.

This recompute is **event-driven** (triggered by inbound/outbound saves),
not a nightly batch job — per the spec ("when inbound/outbound changes,
update this table").

The 日結餘額表 report screen (`reports.closing_view`/`closing_export`,
`templates/reports/closing.html`) queries this table directly, joined to
`Product`/`Warehouse` for the names, filterable by product/warehouse/date
range, exportable to Excel — same query+export shape as the other report
screens.

## GitHub

Pushed to `https://github.com/idemiwang/minierp2` (public). Never commit a
real `.env` — only `.env.example` with placeholders.
