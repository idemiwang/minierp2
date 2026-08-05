/* Outbound approval workflow: Status/ApprovedBy/ApprovedAt on
   OutboundHeader. InboundHeader gets the SAME three columns purely to
   keep v_inoutheader's literal UNION ALL column-symmetric (same trick as
   migration 004's WarehouseId/DocTypeId/Vendor/CustomerId) — Inbound
   never uses the approval workflow, so its rows are always 'APPROVED'.

   Existing rows in both tables backfill to 'APPROVED' (they already
   affected stock under the old unconditional recalculate, so marking
   them approved preserves that with zero disruption). */

ALTER TABLE dbo.OutboundHeader ADD Status NVARCHAR(10) NULL;
GO
ALTER TABLE dbo.OutboundHeader ADD ApprovedBy NVARCHAR(50) NULL;
GO
ALTER TABLE dbo.OutboundHeader ADD ApprovedAt DATETIME2 NULL;
GO

UPDATE dbo.OutboundHeader SET Status = 'APPROVED' WHERE Status IS NULL;
GO

ALTER TABLE dbo.OutboundHeader ALTER COLUMN Status NVARCHAR(10) NOT NULL;
GO
ALTER TABLE dbo.OutboundHeader ADD CONSTRAINT DF_OutboundHeader_Status DEFAULT ('PENDING') FOR Status;
GO
ALTER TABLE dbo.OutboundHeader ADD CONSTRAINT CK_OutboundHeader_Status
    CHECK (Status IN ('PENDING', 'APPROVED', 'REJECTED'));
GO

ALTER TABLE dbo.InboundHeader ADD Status NVARCHAR(10) NULL;
GO
ALTER TABLE dbo.InboundHeader ADD ApprovedBy NVARCHAR(50) NULL;
GO
ALTER TABLE dbo.InboundHeader ADD ApprovedAt DATETIME2 NULL;
GO

UPDATE dbo.InboundHeader SET Status = 'APPROVED' WHERE Status IS NULL;
GO

ALTER TABLE dbo.InboundHeader ALTER COLUMN Status NVARCHAR(10) NOT NULL;
GO
ALTER TABLE dbo.InboundHeader ADD CONSTRAINT DF_InboundHeader_Status DEFAULT ('APPROVED') FOR Status;
GO

/* SQL Server bakes a `SELECT *` view's column list in at CREATE time —
   it does NOT pick up new columns added to the underlying tables later.
   v_inoutheader was created (migration 002) back when InboundHeader/
   OutboundHeader only had 3 columns each; every migration since that
   added columns to either table (004's Warehouse/DocType/Vendor/Customer,
   this one's Status/ApprovedBy/ApprovedAt) needs this refresh or the view
   silently keeps serving the old, narrower column set forever. */
EXEC sp_refreshview 'dbo.v_inoutheader';
GO
EXEC sp_refreshview 'dbo.v_inoutdetail';
GO
