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
avoids diffing added/changed/removed rows. `Product.StockBalance` is
**not** auto-adjusted by inbound/outbound saves — out of scope per the
assignment spec, not an oversight.

## GitHub

Pushed to `https://github.com/idemiwang/minierp2` (public). Never commit a
real `.env` — only `.env.example` with placeholders.
