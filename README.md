# minierp2

A small web-based ERP built with Flask + SQL Server, with a two-level menu:

- **主數據**:物料管理(Product)、員工管理(Employee)— 主檔可新增/修改/刪除;
  明細為唯讀 view,有明細紀錄的主檔不可刪除。
- **交易數據**:入庫管理(Inbound)、出庫管理(Outbound)— header + line-item
  單據,可新增/修改/刪除,並可匯出 Excel 單據式報表。
- **報表查詢**:入出單據、入出明細 — 查詢 `v_inoutheader`/`v_inoutdetail`
  (入庫/出庫 UNION ALL 而成的 view),可篩選查詢並匯出 Excel。

Requires a simple login (single account, credentials in `.env`).

## Setup

```bash
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
cp .env.example .env
```

Fill in `.env`:
- `DB_SERVER` / `DB_PORT` / `DB_NAME` / `DB_USER` / `DB_PASSWORD` — your
  SQL Server connection.
- `APP_SECRET_KEY` — any random string (`python3 -c "import secrets; print(secrets.token_hex(24))"`).
- `APP_USERNAME` / `APP_PASSWORD_HASH` — the app's login. Generate the hash:
  ```bash
  ./venv/bin/python3 -c "from werkzeug.security import generate_password_hash; print(generate_password_hash('your-password', method='pbkdf2:sha256'))"
  ```

First run (creates the schema if it isn't there yet):
```bash
./venv/bin/python3 scripts/apply_migrations.py
```

Run the app:
```bash
./venv/bin/python3 app.py
```
Then open http://127.0.0.1:5050.

See [CLAUDE.md](CLAUDE.md) for architecture/convention details and
[SKILL.md](SKILL.md) for the pattern used to add a new module.
