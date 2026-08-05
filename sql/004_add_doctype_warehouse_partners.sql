/* Adds 單別(DocType) / 倉別(Warehouse) / 客戶(Customer) / 廠商(Vendor) master
   data, per-warehouse stock (ProductWarehouseStock), and the matching
   header columns on InboundHeader/OutboundHeader.

   InboundHeader and OutboundHeader intentionally get the SAME four new
   columns (WarehouseId, DocTypeId, VendorId, CustomerId) so they stay
   column-for-column symmetric — v_inoutheader's literal
   `SELECT * FROM InboundHeader UNION ALL SELECT * FROM OutboundHeader`
   keeps working unchanged. InboundHeader only ever populates VendorId;
   OutboundHeader only ever populates CustomerId.

   There's already live data (8 inbound / 1 outbound headers), so the new
   NOT NULL columns are added nullable first, backfilled to a default
   warehouse/doc-type, then locked to NOT NULL. */

CREATE TABLE dbo.Warehouse (
    WarehouseId   NVARCHAR(40)  NOT NULL PRIMARY KEY,
    WarehouseName NVARCHAR(100) NOT NULL
);
GO

CREATE TABLE dbo.DocType (
    DocTypeId   NVARCHAR(40)  NOT NULL PRIMARY KEY,
    DocTypeName NVARCHAR(100) NOT NULL,
    Direction   NVARCHAR(3)   NOT NULL CHECK (Direction IN ('IN', 'OUT'))
);
GO

CREATE TABLE dbo.Customer (
    CustomerId   NVARCHAR(40)  NOT NULL PRIMARY KEY,
    CustomerName NVARCHAR(100) NOT NULL,
    Phone        NVARCHAR(50)  NULL
);
GO

CREATE TABLE dbo.Vendor (
    VendorId   NVARCHAR(40)  NOT NULL PRIMARY KEY,
    VendorName NVARCHAR(100) NOT NULL,
    Phone      NVARCHAR(50)  NULL
);
GO

CREATE TABLE dbo.ProductWarehouseStock (
    ProductId    NVARCHAR(40)  NOT NULL,
    WarehouseId  NVARCHAR(40)  NOT NULL,
    StockBalance DECIMAL(18,3) NOT NULL DEFAULT (0),
    CONSTRAINT PK_ProductWarehouseStock PRIMARY KEY (ProductId, WarehouseId),
    CONSTRAINT FK_ProductWarehouseStock_Product FOREIGN KEY (ProductId)
        REFERENCES dbo.Product (ProductId),
    CONSTRAINT FK_ProductWarehouseStock_Warehouse FOREIGN KEY (WarehouseId)
        REFERENCES dbo.Warehouse (WarehouseId)
);
GO

INSERT INTO dbo.Warehouse (WarehouseId, WarehouseName) VALUES ('W0001', N'總倉');
GO

INSERT INTO dbo.DocType (DocTypeId, DocTypeName, Direction) VALUES
    ('D0001', N'採購入庫', 'IN'),
    ('D0002', N'退貨入庫', 'IN'),
    ('D0003', N'調撥入庫', 'IN'),
    ('D0004', N'盤盈入庫', 'IN'),
    ('D0005', N'銷售出庫', 'OUT'),
    ('D0006', N'退貨出庫', 'OUT'),
    ('D0007', N'調撥出庫', 'OUT'),
    ('D0008', N'盤虧出庫', 'OUT');
GO

ALTER TABLE dbo.InboundHeader ADD WarehouseId NVARCHAR(40) NULL;
GO
ALTER TABLE dbo.InboundHeader ADD DocTypeId NVARCHAR(40) NULL;
GO
ALTER TABLE dbo.InboundHeader ADD VendorId NVARCHAR(40) NULL;
GO
ALTER TABLE dbo.InboundHeader ADD CustomerId NVARCHAR(40) NULL;
GO

ALTER TABLE dbo.OutboundHeader ADD WarehouseId NVARCHAR(40) NULL;
GO
ALTER TABLE dbo.OutboundHeader ADD DocTypeId NVARCHAR(40) NULL;
GO
ALTER TABLE dbo.OutboundHeader ADD VendorId NVARCHAR(40) NULL;
GO
ALTER TABLE dbo.OutboundHeader ADD CustomerId NVARCHAR(40) NULL;
GO

UPDATE dbo.InboundHeader SET WarehouseId = 'W0001', DocTypeId = 'D0001' WHERE WarehouseId IS NULL;
GO

UPDATE dbo.OutboundHeader SET WarehouseId = 'W0001', DocTypeId = 'D0005' WHERE WarehouseId IS NULL;
GO

ALTER TABLE dbo.InboundHeader ALTER COLUMN WarehouseId NVARCHAR(40) NOT NULL;
GO
ALTER TABLE dbo.InboundHeader ALTER COLUMN DocTypeId NVARCHAR(40) NOT NULL;
GO
ALTER TABLE dbo.OutboundHeader ALTER COLUMN WarehouseId NVARCHAR(40) NOT NULL;
GO
ALTER TABLE dbo.OutboundHeader ALTER COLUMN DocTypeId NVARCHAR(40) NOT NULL;
GO

ALTER TABLE dbo.InboundHeader ADD CONSTRAINT FK_InboundHeader_Warehouse
    FOREIGN KEY (WarehouseId) REFERENCES dbo.Warehouse (WarehouseId);
GO
ALTER TABLE dbo.InboundHeader ADD CONSTRAINT FK_InboundHeader_DocType
    FOREIGN KEY (DocTypeId) REFERENCES dbo.DocType (DocTypeId);
GO
ALTER TABLE dbo.InboundHeader ADD CONSTRAINT FK_InboundHeader_Vendor
    FOREIGN KEY (VendorId) REFERENCES dbo.Vendor (VendorId);
GO
ALTER TABLE dbo.InboundHeader ADD CONSTRAINT FK_InboundHeader_Customer
    FOREIGN KEY (CustomerId) REFERENCES dbo.Customer (CustomerId);
GO

ALTER TABLE dbo.OutboundHeader ADD CONSTRAINT FK_OutboundHeader_Warehouse
    FOREIGN KEY (WarehouseId) REFERENCES dbo.Warehouse (WarehouseId);
GO
ALTER TABLE dbo.OutboundHeader ADD CONSTRAINT FK_OutboundHeader_DocType
    FOREIGN KEY (DocTypeId) REFERENCES dbo.DocType (DocTypeId);
GO
ALTER TABLE dbo.OutboundHeader ADD CONSTRAINT FK_OutboundHeader_Vendor
    FOREIGN KEY (VendorId) REFERENCES dbo.Vendor (VendorId);
GO
ALTER TABLE dbo.OutboundHeader ADD CONSTRAINT FK_OutboundHeader_Customer
    FOREIGN KEY (CustomerId) REFERENCES dbo.Customer (CustomerId);
GO

/* InventoryDailyClosing is entirely derived/recomputed by
   inventory_closing.recalculate() — never hand-entered — so it's safe to
   drop and recreate with WarehouseId added to its key. The app re-derives
   every row the next time it recomputes each product/warehouse pair. */
DROP TABLE dbo.InventoryDailyClosing;
GO

CREATE TABLE dbo.InventoryDailyClosing (
    ClosingDate      DATE          NOT NULL,
    ProductId        NVARCHAR(40)  NOT NULL,
    WarehouseId      NVARCHAR(40)  NOT NULL,
    OpeningQuantity  DECIMAL(18,3) NOT NULL,
    InboundQuantity  DECIMAL(18,3) NOT NULL,
    OutboundQuantity DECIMAL(18,3) NOT NULL,
    ClosingQuantity  DECIMAL(18,3) NOT NULL,
    CONSTRAINT PK_InventoryDailyClosing PRIMARY KEY (ClosingDate, ProductId, WarehouseId),
    CONSTRAINT FK_InventoryDailyClosing_Product FOREIGN KEY (ProductId)
        REFERENCES dbo.Product (ProductId),
    CONSTRAINT FK_InventoryDailyClosing_Warehouse FOREIGN KEY (WarehouseId)
        REFERENCES dbo.Warehouse (WarehouseId)
);
GO
