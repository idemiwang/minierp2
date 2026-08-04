/* minierp2 — initial schema for kimtae, mirroring the biz00 mini-ERP exercise. */

CREATE TABLE dbo.Employee (
    EmployeeId   NVARCHAR(40)  NOT NULL PRIMARY KEY,
    EmployeeName NVARCHAR(100) NOT NULL,
    Email        NVARCHAR(255) NULL
);
GO

CREATE TABLE dbo.Product (
    ProductId    NVARCHAR(40)  NOT NULL PRIMARY KEY,
    ProductName  NVARCHAR(200) NOT NULL,
    StockBalance DECIMAL(18,3) NOT NULL DEFAULT (0)
);
GO

CREATE TABLE dbo.InboundHeader (
    InboundId   NVARCHAR(40) NOT NULL PRIMARY KEY,
    InboundDate DATE         NOT NULL,
    EmployeeId  NVARCHAR(40) NOT NULL,
    CONSTRAINT FK_InboundHeader_Employee FOREIGN KEY (EmployeeId)
        REFERENCES dbo.Employee (EmployeeId)
);
GO

CREATE TABLE dbo.OutboundHeader (
    OutboundId   NVARCHAR(40) NOT NULL PRIMARY KEY,
    OutboundDate DATE         NOT NULL,
    EmployeeId   NVARCHAR(40) NOT NULL,
    CONSTRAINT FK_OutboundHeader_Employee FOREIGN KEY (EmployeeId)
        REFERENCES dbo.Employee (EmployeeId)
);
GO

CREATE TABLE dbo.InboundDetail (
    InboundId   NVARCHAR(40)  NOT NULL,
    LineNum     SMALLINT      NOT NULL,
    ProductId   NVARCHAR(40)  NOT NULL,
    ProductName NVARCHAR(200) NOT NULL,
    Quantity    DECIMAL(18,3) NOT NULL,
    CONSTRAINT PK_InboundDetail PRIMARY KEY (InboundId, LineNum),
    CONSTRAINT FK_InboundDetail_InboundHeader FOREIGN KEY (InboundId)
        REFERENCES dbo.InboundHeader (InboundId) ON DELETE CASCADE,
    CONSTRAINT FK_InboundDetail_Product FOREIGN KEY (ProductId)
        REFERENCES dbo.Product (ProductId)
);
GO

CREATE TABLE dbo.OutboundDetail (
    OutboundId  NVARCHAR(40)  NOT NULL,
    LineNum     SMALLINT      NOT NULL,
    ProductId   NVARCHAR(40)  NOT NULL,
    ProductName NVARCHAR(200) NOT NULL,
    Quantity    DECIMAL(18,3) NOT NULL,
    CONSTRAINT PK_OutboundDetail PRIMARY KEY (OutboundId, LineNum),
    CONSTRAINT FK_OutboundDetail_OutboundHeader FOREIGN KEY (OutboundId)
        REFERENCES dbo.OutboundHeader (OutboundId) ON DELETE CASCADE,
    CONSTRAINT FK_OutboundDetail_Product FOREIGN KEY (ProductId)
        REFERENCES dbo.Product (ProductId)
);
GO
