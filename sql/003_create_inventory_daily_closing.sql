/* Daily closing balance ledger — one row per (ClosingDate, ProductId).
   Populated/recomputed by inventory_closing.recalculate(), never hand-edited. */

CREATE TABLE dbo.InventoryDailyClosing (
    ClosingDate      DATE          NOT NULL,
    ProductId        NVARCHAR(40)  NOT NULL,
    OpeningQuantity  DECIMAL(18,3) NOT NULL,
    InboundQuantity  DECIMAL(18,3) NOT NULL,
    OutboundQuantity DECIMAL(18,3) NOT NULL,
    ClosingQuantity  DECIMAL(18,3) NOT NULL,
    CONSTRAINT PK_InventoryDailyClosing PRIMARY KEY (ClosingDate, ProductId),
    CONSTRAINT FK_InventoryDailyClosing_Product FOREIGN KEY (ProductId)
        REFERENCES dbo.Product (ProductId)
);
GO
