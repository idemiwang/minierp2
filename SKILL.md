---
name: minierp2-add-module
description: Step-by-step pattern for adding a new master-data or transaction (header/detail) module to the minierp2 Flask app, matching the existing Product/Employee/Inbound/Outbound blueprints.
---

# Adding a module to minierp2

Use this whenever asked to add a new menu item / data module to this app —
a new master table, or a new header+detail transaction type.

## When to use

- "Add a new master data screen for X"
- "Add a new transaction type like inbound/outbound but for Y"
- Any request to extend the two-level menu with a new function

## Steps — master data (like Product / Employee)

1. **Table**: add a `sql/NNN_*.sql` migration (next number after the last
   file in `sql/`), apply with `scripts/apply_migrations.py`. Re-run
   `scripts/introspect_schema.py` afterward to refresh `schema_dump.json`.
2. **ID generation**: if the PK isn't IDENTITY, add a `next_x_id()` to
   `id_generator.py` following the existing `P0001`/`E0001` pattern.
3. **Blueprint**: copy `blueprints/product.py` as a template —
   `list_view`, `create_view`, `edit_view`, `delete_view`, `detail_view`.
   Keep the normalized `form_values` dict pattern so the form template
   doesn't care whether it's rendering a fresh form or a validation-failed
   repost.
4. **Delete guard**: if this master data has a related transaction view
   (like `v_inoutdetail`/`v_inoutheader`), pre-check `COUNT(*)` before
   delete and flash a friendly message — don't let a raw FK violation
   surface to the user. Wrap the actual `DELETE` in a
   `try/except pytds.tds_base.IntegrityError` as a fallback.
5. **Templates**: `templates/<module>/list.html`, `form.html`,
   `detail.html` — copy `templates/product/*.html` and adjust field names.
6. **Register**: add the blueprint import + `app.register_blueprint(...)`
   in `app.py`, and a new entry under the right group in `MENU`.

## Steps — transaction type (like Inbound / Outbound)

Same as above, plus:

1. **Header + detail tables** with a line-item child table (`LineNum` +
   FK back to the header), matching `InboundHeader`/`InboundDetail`.
2. **Blueprint**: copy `blueprints/inbound.py`. Keep the `_parse_lines()`
   helper that validates posted `product_id[]`/`quantity[]` arrays against
   a `product_map` built server-side (never trust a client-supplied product
   name/price — always re-look-up from the DB).
3. **Save transaction**: `db.transaction()` block — insert/update header,
   then `DELETE` all existing detail rows for that key and re-insert the
   current grid, in that order, inside the same transaction.
4. **Dynamic line grid**: copy the `<template id="line-template">` +
   add/remove-row JS from `templates/inbound/form.html` — it's plain
   `product_id[]`/`quantity[]` array-name inputs, no per-row indexing
   needed.
5. **Excel export**: use `excel.exporters.export_document()` for a
   per-record "document style" export (header block + line table),
   reachable from the detail view page.
6. **Register**: same as master data — blueprint + `MENU` entry. Add both
   a `list_view` route and a `.../<id>/export` route.

## Steps — report/query screen (like 入出單據 / 入出明細)

1. Query the existing view (or a new one, added via migration) with a
   `_filtered_rows(args)` helper that builds a `WHERE` clause from request
   args — see `blueprints/reports.py` for the pattern.
2. Two routes minimum: the query/HTML view and a `.../export` route using
   `excel.exporters.export_table()` (plain tabular, not document-style).
3. Register under `報表查詢` in `MENU`.

## Output checklist

- [ ] Migration file applied, `schema_dump.json` refreshed
- [ ] Blueprint registered in `app.py`, `MENU` entry added
- [ ] Templates follow the existing list/form/detail split
- [ ] Delete guard (if applicable) tested against a row with dependents
- [ ] Excel export opens correctly and reflects on-screen data
- [ ] `CLAUDE.md` updated if the schema or a business rule changed
