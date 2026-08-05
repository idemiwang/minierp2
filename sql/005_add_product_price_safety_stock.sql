/* SafetyStock (安全庫存) drives the 低庫存警示 report; UnitPrice drives the
   employee-performance / customer-ranking sales-value reports. Both get a
   zero default so existing rows backfill in the same statement. */

ALTER TABLE dbo.Product ADD SafetyStock DECIMAL(18,3) NOT NULL DEFAULT (0);
GO

ALTER TABLE dbo.Product ADD UnitPrice DECIMAL(18,2) NOT NULL DEFAULT (0);
GO
