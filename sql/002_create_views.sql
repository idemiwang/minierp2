/* v_inoutheader / v_inoutdetail — exactly the UNION ALL the spec calls for.
   Note: InboundHeader's PK column is named InboundId, OutboundHeader's is
   OutboundId; UNION ALL matches columns positionally, so the view exposes
   both under the first query's column name (InboundId / InboundId-less
   detail equivalents). The app treats that column as a generic transaction
   id — see reports blueprint. */

CREATE VIEW dbo.v_inoutheader AS
SELECT * FROM dbo.InboundHeader
UNION ALL
SELECT * FROM dbo.OutboundHeader;
GO

CREATE VIEW dbo.v_inoutdetail AS
SELECT * FROM dbo.InboundDetail
UNION ALL
SELECT * FROM dbo.OutboundDetail;
GO
