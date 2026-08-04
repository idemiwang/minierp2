# CLAUDE.md

Context for Claude Code (or any future assistant) working in this repo.

**Keep this file and `SKILL.md` up to date.** Whenever the schema, routes,
or conventions below change, update both files in the same change — that's
an explicit project convention here, not optional cleanup.

## What this repo is

`minierp2` is a small web-based ERP (Flask + SQL Server) covering:
master data (Product / Employee), transactional data (Inbound / Outbound
documents with line items), and two report/query screens over union views.
See `SKILL.md` for the step-by-step pattern used to add a new module.

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

## Transactional save pattern (Inbound / Outbound)

Header + line-item saves happen inside `db.transaction()`: on update, all
existing detail rows for that document are deleted and the current grid
state is re-inserted — simplest correct approach for a small line grid,
avoids diffing added/changed/removed rows.

## Daily closing balance (dbo.InventoryDailyClosing) and StockBalance sync

`inventory_closing.recalculate(product_id)` is called for every
`ProductId` touched by an inbound/outbound create/edit/delete, **inside
the same `db.transaction()` block** as the header/detail save (so a
closing-table failure rolls back the whole save).

**Users often enter documents out of date order** (a backdated document
can be saved after later-dated ones already exist). `recalculate()`
handles this by never doing an incremental patch — it always fully rebuilds
that one product's whole daily-closing history in calendar-date order:

1. Sum inbound/outbound quantities per calendar day for that product (both
   sides, always — the closing balance depends on both regardless of which
   blueprint triggered the call).
2. Delete all existing `InventoryDailyClosing` rows for that product.
3. If it has no transactions left, stop after setting `StockBalance = 0`
   (this branch only happens when a save/delete just removed a product's
   *last* transaction — `recalculate()` is never called for a product
   with no history at all, since such a product is never in a
   document's affected-products set to begin with).
4. Otherwise walk day-by-day from its first activity date through
   **today**, `opening = previous day's closing` (0 on day one),
   `closing = opening + inbound - outbound`, inserting one row per day
   (including zero-movement days, carried forward) — this is what makes
   entry order irrelevant, since the rebuild always replays in date order
   regardless of the order documents were saved in.
5. `Product.StockBalance` is set to the final day's `ClosingQuantity`.

**Behavior worth knowing (not a bug)**: since the rebuild always starts
from an opening balance of 0 on a product's first-ever activity date, a
manually-typed `StockBalance` on the Product form only holds until that
product's *first* inbound/outbound is saved — after that, `StockBalance`
is fully derived from recorded movements.

This recompute is **event-driven** (triggered by inbound/outbound saves),
not a nightly batch job — per the spec ("when inbound/outbound changes,
update this table"). There's no scheduled job advancing "today" on its
own, so a product's last row only reflects the real current date once
something touches one of its documents again.

The 日結餘額表 report screen (`reports.closing_view`/`closing_export`,
`templates/reports/closing.html`) queries this table directly, joined to
`Product` for the name, filterable by product/date range, exportable to
Excel — same query+export shape as the other two report screens.

## GitHub

Pushed to `https://github.com/idemiwang/minierp2` (public). Never commit a
real `.env` — only `.env.example` with placeholders.
