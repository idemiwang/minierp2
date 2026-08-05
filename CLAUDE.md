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

## Login and roles

Two shared role accounts (not one per real Employee) — `EMPLOYEE_USERNAME`/
`EMPLOYEE_PASSWORD_HASH` and `MANAGER_USERNAME`/`MANAGER_PASSWORD_HASH` in
`.env`, checked in `auth.py`'s `ROLE_ACCOUNTS`. Login sets both
`session["user"]` (display/audit name) and `session["role"]`
(`"employee"`/`"manager"`). `app.before_request` blocks every route except
`/login` and static assets until `session["user"]` is set (unchanged).
`auth.manager_required` is a second decorator for routes only a manager
may hit (currently just outbound approve/reject) — checked server-side,
never just by hiding a button in the template. The navbar
(`templates/base.html`) shows a different fun title per role by reading
`session.get('role')` directly in Jinja (`session` is already a Jinja
global, no extra context processor needed).

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

## Low-stock alerts, sales value, and stock-check warnings

`Product` has two more fields (migration 005, zero-default so they
backfilled cleanly): `SafetyStock` (安全庫存) and `UnitPrice` (單價).

- **庫存警示** (`reports.low_stock_view`): products where the global
  rollup `StockBalance <= SafetyStock` — a simple, non-per-warehouse
  comparison (per-warehouse thresholds were out of scope for this pass).
- **員工業績** / **客戶排行** (`reports.employee_performance_view` /
  `customer_ranking_view`): `SUM(OutboundDetail.Quantity *
  Product.UnitPrice)` grouped by employee / customer, via `Employee`/
  `Customer` `LEFT JOIN OutboundHeader` (date-range filter lives in the
  `ON` clause, not `WHERE`, so employees/customers with zero sales in
  range still appear) `LEFT JOIN OutboundDetail LEFT JOIN Product`. The
  bonus-% multiplier on the employee report is a **client-side-only**
  `<input>` (`templates/reports/employee_performance.html`) — never sent
  to the server or stored, purely a live JS calculation over the
  server-rendered sales totals.
- **Outbound stock-check** (`blueprints/outbound.py`,
  `_stock_shortfall_warnings`): before saving, compares each line's
  quantity to that `(ProductId, WarehouseId)` pair's *current*
  `ProductWarehouseStock.StockBalance`. This is advisory only — flashes a
  `"warning"`-category message listing short items but **never blocks the
  save** (backorders are tolerated, matching pre-existing negative-stock
  data). It checks the pre-save balance and doesn't try to net out an
  edit's own prior line — a deliberate approximation, not a precise
  guarantee.

## Outbound approval workflow (manager sign-off)

Outbound (only — Inbound is untouched) now requires manager approval
before it affects stock, per a real-ERP convention. `OutboundHeader` (and,
purely to keep `v_inoutheader`'s positional `UNION ALL` valid, the unused
`InboundHeader` columns too — see migration 006) carries:
- `Status` (`PENDING` / `APPROVED` / `REJECTED`) — new outbound docs are
  created `PENDING`; Inbound rows are always backfilled/defaulted to
  `APPROVED` since that document type never goes through this workflow.
- `ApprovedBy` (login username) / `ApprovedAt` (timestamp) — set together
  whenever a manager approves or rejects; both `NULL` while `PENDING`.

**Key design insight**: `inventory_closing.recalculate()` already does a
full rebuild-from-DB every time it runs, so the *only* change needed was
adding `AND h.Status = 'APPROVED'` to its outbound query
(`inventory_closing.py`). That single filter makes every transition —
create-as-pending, approve, reject, edit-an-approved-doc-back-to-pending,
delete — "just work" through the exact same `recalculate()` call already
wired into every outbound save/delete path. There is no special-case
stock-reversal code anywhere: a doc's stock effect is purely a function of
whatever `Status` it currently holds at recalculate time.

Editing an outbound document — of any prior status — always resets it to
`Status='PENDING'` and clears `ApprovedBy`/`ApprovedAt`, requiring
re-approval; the 經手員工 (`EmployeeId`) dropdown itself stays freely
editable regardless of role.

Rejected documents are **kept, not deleted** — they're an editable audit
record (same as any other status, editing one resets it to `PENDING`).

Routes (`blueprints/outbound.py`): `POST /outbound/<id>/approve` and
`POST /outbound/<id>/reject`, both decorated `@auth.manager_required` (a
`session.get("role") != "manager"` check that redirects with a flash
error — enforced server-side regardless of what buttons the UI shows).
`GET /outbound/pending` lists all `PENDING` docs; visible to everyone for
transparency, but the Approve/Reject buttons only render for
`session.get('role') == 'manager'` in `templates/outbound/pending.html`
and `templates/outbound/detail.html`.

Any report/dashboard query computing a "sales value" from
`OutboundDetail.Quantity * Product.UnitPrice` (員工業績, 客戶排行,
dashboard 本月/本年業績, dashboard 熱銷排行) filters to
`Status = 'APPROVED'` — a pending or rejected order isn't a real sale yet.
The raw 入出單據 union report (`v_inoutheader`) is **not** filtered at the
query level (kept as a literal spec-mandated union), but does show a
Status column for visibility. 日結餘額表 needed no changes since it's
already correct via the filtered `recalculate()`.

## Dashboard (首頁) and 年度分析

`blueprints/dashboard.py` (`index_view`) is now the `/` route — replaces
the old plain redirect to the product list. Shows master-data counts,
this-month/this-year sales totals (same quantity×price formula as the
performance reports), the low-stock count (linking to 庫存警示), and a
top-5 best-sellers table (ranked by total outbound *quantity*, not sales
value — "熱銷" reads as "moves a lot," not "worth a lot").

年度分析 (`reports.annual_view`) shows a yearly-totals table (all years
with any outbound data) plus a **Chart.js** bar chart (`templates/reports/
annual.html`, loaded via CDN like Bootstrap/Google Fonts — first chart
library in the app) of the selected year's monthly totals. Selecting a
year re-submits the same GET route with `?year=`; months with no data are
zero-filled in Python before charting (`monthly_totals` is always a
12-element list, Jan→Dec).

## Vendor / Customer detail pages

Mirror `product.py`/`employee.py`'s detail pattern: `vendor.detail_view`
lists that vendor's `InboundHeader` history; `customer.detail_view` lists
that customer's `OutboundHeader` history. Both list templates link their
ID column to the detail page.

## GitHub

Pushed to `https://github.com/idemiwang/minierp2` (public). Never commit a
real `.env` — only `.env.example` with placeholders.
