-- Extreme T-SQL stress sample 1
-- Purpose: broad operational workflow with temp tables, recursive CTEs, table variables,
-- JSON/XML handling, dynamic SQL, MERGE, transactions, error handling, window functions,
-- CROSS/OUTER APPLY, PIVOT, UNPIVOT, and multi-batch administrative patterns.

SET NOCOUNT ON;
SET XACT_ABORT ON;

IF OBJECT_ID('tempdb..#StageOrders') IS NOT NULL
    DROP TABLE #StageOrders;

IF OBJECT_ID('tempdb..#StageAudit') IS NOT NULL
    DROP TABLE #StageAudit;

CREATE TABLE #StageOrders
(
    StageOrderId BIGINT IDENTITY(1, 1) NOT NULL PRIMARY KEY,
    SourceSystemCode NVARCHAR(30) NOT NULL,
    OrderId BIGINT NOT NULL,
    ParentOrderId BIGINT NULL,
    CustomerId BIGINT NOT NULL,
    SalesRepId INT NULL,
    RegionCode NVARCHAR(10) NULL,
    CurrencyCode CHAR(3) NOT NULL,
    OrderDate DATETIME2(3) NOT NULL,
    RequestedShipDate DATETIME2(3) NULL,
    OrderStatus NVARCHAR(30) NOT NULL,
    PriorityCode NVARCHAR(20) NULL,
    OrderAmount DECIMAL(19, 4) NOT NULL,
    TaxAmount DECIMAL(19, 4) NOT NULL,
    DiscountAmount DECIMAL(19, 4) NOT NULL,
    ShippingAmount DECIMAL(19, 4) NOT NULL,
    NetAmount AS (OrderAmount + TaxAmount + ShippingAmount - DiscountAmount) PERSISTED,
    AttributesJson NVARCHAR(MAX) NULL,
    ExtraXml XML NULL,
    LoadBatchId UNIQUEIDENTIFIER NOT NULL DEFAULT NEWID(),
    CreatedUtc DATETIME2(3) NOT NULL DEFAULT SYSUTCDATETIME(),
    RowHash VARBINARY(32) NULL
);

CREATE TABLE #StageAudit
(
    AuditId BIGINT IDENTITY(1, 1) PRIMARY KEY,
    AuditUtc DATETIME2(3) NOT NULL DEFAULT SYSUTCDATETIME(),
    AuditAction NVARCHAR(50) NOT NULL,
    AffectedEntity NVARCHAR(128) NOT NULL,
    ReferenceId NVARCHAR(128) NULL,
    AuditPayload NVARCHAR(MAX) NULL
);

DECLARE @RegionFilter TABLE
(
    RegionCode NVARCHAR(10) PRIMARY KEY,
    RegionGroup NVARCHAR(30) NOT NULL
);

INSERT INTO @RegionFilter
    (RegionCode, RegionGroup)
VALUES
    (N'NE', N'DOMESTIC'),
    (N'SE', N'DOMESTIC'),
    (N'NW', N'DOMESTIC'),
    (N'INTL', N'INTERNATIONAL'),
    (N'LATAM', N'INTERNATIONAL');

DECLARE @RawOrderFeed TABLE
(
    FeedRowId INT IDENTITY(1, 1) PRIMARY KEY,
    SourceSystemCode NVARCHAR(30) NOT NULL,
    OrderId BIGINT NOT NULL,
    ParentOrderId BIGINT NULL,
    CustomerId BIGINT NOT NULL,
    SalesRepId INT NULL,
    RegionCode NVARCHAR(10) NULL,
    CurrencyCode CHAR(3) NOT NULL,
    OrderDate DATETIME2(3) NOT NULL,
    RequestedShipDate DATETIME2(3) NULL,
    OrderStatus NVARCHAR(30) NOT NULL,
    PriorityCode NVARCHAR(20) NULL,
    OrderAmount DECIMAL(19, 4) NOT NULL,
    TaxAmount DECIMAL(19, 4) NOT NULL,
    DiscountAmount DECIMAL(19, 4) NOT NULL,
    ShippingAmount DECIMAL(19, 4) NOT NULL,
    AttributesJson NVARCHAR(MAX) NULL,
    ExtraXml XML NULL
);

INSERT INTO @RawOrderFeed
    (
    SourceSystemCode,
    OrderId,
    ParentOrderId,
    CustomerId,
    SalesRepId,
    RegionCode,
    CurrencyCode,
    OrderDate,
    RequestedShipDate,
    OrderStatus,
    PriorityCode,
    OrderAmount,
    TaxAmount,
    DiscountAmount,
    ShippingAmount,
    AttributesJson,
    ExtraXml
    )
VALUES
    (N'ERP', 1001001, NULL, 501, 11, N'NE', N'USD', '2025-11-01T08:30:00', '2025-11-05T00:00:00', N'OPEN', N'HIGH', 1250.00, 125.00, 50.00, 35.00, N'{"channel":"web","flags":["rush","vip"],"warehouse":"WH1"}', '<extra><giftWrap>true</giftWrap><source>campaign-a</source></extra>'),
    (N'ERP', 1001002, 1001001, 501, 11, N'NE', N'USD', '2025-11-01T09:00:00', '2025-11-06T00:00:00', N'OPEN', N'HIGH', 275.00, 27.50, 0.00, 10.00, N'{"channel":"web","flags":["upsell"],"warehouse":"WH1"}', '<extra><giftWrap>false</giftWrap><source>campaign-a</source></extra>'),
    (N'CRM', 1002001, NULL, 777, 42, N'INTL', N'EUR', '2025-11-02T14:15:00', '2025-11-10T00:00:00', N'REVIEW', N'MEDIUM', 9800.00, 1960.00, 500.00, 125.00, N'{"channel":"partner","flags":["manual-review"],"warehouse":"WH9"}', '<extra><giftWrap>false</giftWrap><source>partner-x</source></extra>'),
    (N'POS', 1003001, NULL, 888, NULL, N'SE', N'USD', '2025-11-03T16:20:00', NULL, N'COMPLETE', N'LOW', 89.95, 7.20, 5.00, 0.00, N'{"channel":"retail","flags":[],"warehouse":"STORE-17"}', '<extra><giftWrap>false</giftWrap><source>in-store</source></extra>'),
    (N'ERP', 1004001, NULL, 912, 18, N'LATAM', N'BRL', '2025-11-04T07:05:00', '2025-11-12T00:00:00', N'OPEN', N'HIGH', 2300.00, 391.00, 100.00, 85.00, N'{"channel":"mobile","flags":["fraud-check"],"warehouse":"WH3"}', '<extra><giftWrap>true</giftWrap><source>campaign-b</source></extra>');

;WITH
    OrderHierarchy
    AS
    (
                    SELECT
                f.OrderId,
                f.ParentOrderId,
                f.CustomerId,
                CAST(CONCAT(CONVERT(NVARCHAR(20), f.OrderId), N'/') AS NVARCHAR(4000)) AS HierarchyPath,
                0 AS HierarchyLevel
            FROM @RawOrderFeed f
            WHERE f.ParentOrderId IS NULL

        UNION ALL

            SELECT
                c.OrderId,
                c.ParentOrderId,
                c.CustomerId,
                CAST(h.HierarchyPath + CONVERT(NVARCHAR(20), c.OrderId) + N'/' AS NVARCHAR(4000)) AS HierarchyPath,
                h.HierarchyLevel + 1 AS HierarchyLevel
            FROM @RawOrderFeed c
                INNER JOIN OrderHierarchy h
                ON c.ParentOrderId = h.OrderId
    )
INSERT INTO #StageOrders
    (
    SourceSystemCode,
    OrderId,
    ParentOrderId,
    CustomerId,
    SalesRepId,
    RegionCode,
    CurrencyCode,
    OrderDate,
    RequestedShipDate,
    OrderStatus,
    PriorityCode,
    OrderAmount,
    TaxAmount,
    DiscountAmount,
    ShippingAmount,
    AttributesJson,
    ExtraXml,
    RowHash
    )
SELECT
    f.SourceSystemCode,
    f.OrderId,
    f.ParentOrderId,
    f.CustomerId,
    f.SalesRepId,
    f.RegionCode,
    f.CurrencyCode,
    f.OrderDate,
    f.RequestedShipDate,
    f.OrderStatus,
    f.PriorityCode,
    f.OrderAmount,
    f.TaxAmount,
    f.DiscountAmount,
    f.ShippingAmount,
    f.AttributesJson,
    f.ExtraXml,
    HASHBYTES(
        'SHA2_256',
        CONCAT(
            f.SourceSystemCode, N'|', f.OrderId, N'|', f.CustomerId, N'|',
            f.OrderStatus, N'|', f.OrderAmount, N'|', COALESCE(f.RegionCode, N'')
        )
    ) AS RowHash
FROM @RawOrderFeed f
    LEFT JOIN OrderHierarchy h
    ON f.OrderId = h.OrderId
OPTION
(MAXRECURSION
100);

INSERT INTO #StageAudit
    (AuditAction, AffectedEntity, ReferenceId, AuditPayload)
SELECT
    N'LOAD',
    N'#StageOrders',
    CONVERT(NVARCHAR(50), s.OrderId),
    JSON_QUERY(
        CONCAT(
            N'{"customerId":', s.CustomerId,
            N',"status":"', s.OrderStatus,
            N'","priority":"', COALESCE(s.PriorityCode, N''),
            N'","region":"', COALESCE(s.RegionCode, N''), N'"}'
        )
    )
FROM #StageOrders s;

BEGIN TRY
    BEGIN TRANSACTION;

    ;WITH
    ParsedAttributes
    AS
    (
        SELECT
            s.StageOrderId,
            s.OrderId,
            s.CustomerId,
            JSON_VALUE(s.AttributesJson, '$.channel') AS SalesChannel,
            JSON_VALUE(s.AttributesJson, '$.warehouse') AS WarehouseCode,
            TRY_CAST(JSON_VALUE(s.AttributesJson, '$.priorityScore') AS INT) AS PriorityScore,
            s.OrderStatus,
            s.PriorityCode,
            s.NetAmount
        FROM #StageOrders s
    ),
    XmlAttributes
    AS
    (
        SELECT
            s.StageOrderId,
            s.OrderId,
            x.n.value('(giftWrap/text())[1]', 'NVARCHAR(10)') AS GiftWrapFlag,
            x.n.value('(source/text())[1]', 'NVARCHAR(100)') AS CampaignSource
        FROM #StageOrders s
        OUTER APPLY s.ExtraXml.nodes('/extra') AS x(n)
    ),
    EnrichedOrders
    AS
    (
        SELECT
            p.StageOrderId,
            p.OrderId,
            p.CustomerId,
            p.SalesChannel,
            p.WarehouseCode,
            p.PriorityScore,
            p.OrderStatus,
            p.PriorityCode,
            p.NetAmount,
            xa.GiftWrapFlag,
            xa.CampaignSource,
            rf.RegionGroup,
            DENSE_RANK() OVER (
                PARTITION BY p.CustomerId
                ORDER BY p.NetAmount DESC, p.OrderId DESC
            ) AS SpendRankPerCustomer,
            SUM(p.NetAmount) OVER (
                PARTITION BY p.CustomerId
            ) AS CustomerTotalNetAmount
        FROM ParsedAttributes p
            LEFT JOIN XmlAttributes xa
            ON p.StageOrderId = xa.StageOrderId
            LEFT JOIN @RegionFilter rf
            ON rf.RegionCode = (
                SELECT TOP (1)
                s2.RegionCode
            FROM #StageOrders s2
            WHERE s2.StageOrderId = p.StageOrderId
            )
    ),
    CustomerSummary
    AS
    (
        SELECT
            eo.CustomerId,
            COUNT(*) AS OrderCount,
            SUM(eo.NetAmount) AS TotalNetAmount,
            MAX(eo.NetAmount) AS MaxNetAmount,
            MAX(CASE WHEN eo.SpendRankPerCustomer = 1 THEN eo.OrderId END) AS TopOrderId
        FROM EnrichedOrders eo
        GROUP BY eo.CustomerId
    )
SELECT
    cs.CustomerId,
    cs.OrderCount,
    cs.TotalNetAmount,
    cs.MaxNetAmount,
    cs.TopOrderId,
    eo.SalesChannel,
    eo.WarehouseCode,
    eo.RegionGroup,
    eo.GiftWrapFlag,
    eo.CampaignSource
INTO #CustomerOperationalSnapshot
FROM CustomerSummary cs
    OUTER APPLY
    (
        SELECT TOP (1)
        e2.SalesChannel,
        e2.WarehouseCode,
        e2.RegionGroup,
        e2.GiftWrapFlag,
        e2.CampaignSource
    FROM EnrichedOrders e2
    WHERE e2.CustomerId = cs.CustomerId
    ORDER BY e2.NetAmount DESC, e2.OrderId DESC
    ) eo;

    MERGE dbo.CustomerOrderSummary AS target
    USING
    (
        SELECT
    cos.CustomerId,
    cos.OrderCount,
    cos.TotalNetAmount,
    cos.MaxNetAmount,
    cos.TopOrderId,
    cos.SalesChannel,
    cos.WarehouseCode,
    cos.RegionGroup,
    SYSUTCDATETIME() AS SnapshotUtc
FROM #CustomerOperationalSnapshot cos
    ) AS source
        ON target.CustomerId = source.CustomerId
    WHEN MATCHED AND
    (
        target.OrderCount <> source.OrderCount
    OR target.TotalNetAmount <> source.TotalNetAmount
    OR target.TopOrderId <> source.TopOrderId
    )
        THEN UPDATE SET
            target.OrderCount = source.OrderCount,
            target.TotalNetAmount = source.TotalNetAmount,
            target.MaxNetAmount = source.MaxNetAmount,
            target.TopOrderId = source.TopOrderId,
            target.PreferredChannel = source.SalesChannel,
            target.PrimaryWarehouse = source.WarehouseCode,
            target.RegionGroup = source.RegionGroup,
            target.LastRefreshUtc = source.SnapshotUtc
    WHEN NOT MATCHED BY TARGET
        THEN INSERT
        (
            CustomerId,
            OrderCount,
            TotalNetAmount,
            MaxNetAmount,
            TopOrderId,
            PreferredChannel,
            PrimaryWarehouse,
            RegionGroup,
            LastRefreshUtc
        )
        VALUES
        (
            source.CustomerId,
            source.OrderCount,
            source.TotalNetAmount,
            source.MaxNetAmount,
            source.TopOrderId,
            source.SalesChannel,
            source.WarehouseCode,
            source.RegionGroup,
            source.SnapshotUtc
        )
    WHEN NOT MATCHED BY SOURCE AND target.IsActive = 1
        THEN UPDATE SET
            target.IsActive = 0,
            target.LastRefreshUtc = SYSUTCDATETIME()
    OUTPUT
        $action,
        inserted.CustomerId,
        deleted.CustomerId,
        inserted.LastRefreshUtc
    INTO dbo.CustomerOrderSummaryAudit
    (
        MergeAction,
        InsertedCustomerId,
        DeletedCustomerId,
        MergeUtc
    );

    WITH
    PivotSource
    AS
    (
        SELECT
            s.CustomerId,
            s.OrderStatus,
            s.NetAmount
        FROM #StageOrders s
    )
SELECT
    p.CustomerId,
    COALESCE([OPEN], 0.00) AS OpenAmount,
    COALESCE([REVIEW], 0.00) AS ReviewAmount,
    COALESCE([COMPLETE], 0.00) AS CompleteAmount
INTO #PivotedOrderStatusAmounts
FROM PivotSource src
    PIVOT
    (
        SUM(NetAmount)
        FOR OrderStatus IN ([OPEN], [REVIEW], [COMPLETE])
    ) p;

    WITH
    UnpivotSource
    AS
    (
        SELECT
            p.CustomerId,
            p.OpenAmount,
            p.ReviewAmount,
            p.CompleteAmount
        FROM #PivotedOrderStatusAmounts p
    )
SELECT
    u.CustomerId,
    u.StatusName,
    u.StatusAmount
INTO #UnpivotedStatusAmounts
FROM UnpivotSource
    UNPIVOT
    (
        StatusAmount
        FOR StatusName IN (OpenAmount, ReviewAmount, CompleteAmount)
    ) u;

    DECLARE @DynamicSql NVARCHAR(MAX);
    DECLARE @DynamicParams NVARCHAR(MAX);
    DECLARE @StatusThreshold DECIMAL(19, 4) = 1000.00;

    SET @DynamicSql = N'
        INSERT INTO #StageAudit (AuditAction, AffectedEntity, ReferenceId, AuditPayload)
        SELECT
            N''STATUS_THRESHOLD'',
            N''#UnpivotedStatusAmounts'',
            CONVERT(NVARCHAR(128), CustomerId),
            CONCAT(N''{"status":"'', StatusName, N''","amount":'', CONVERT(NVARCHAR(50), StatusAmount), N''}'')
        FROM #UnpivotedStatusAmounts
        WHERE StatusAmount >= @StatusThreshold;';

    SET @DynamicParams = N'@StatusThreshold DECIMAL(19,4)';

    EXEC sys.sp_executesql
        @stmt = @DynamicSql,
        @params = @DynamicParams,
        @StatusThreshold = @StatusThreshold;

    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    IF @@TRANCOUNT > 0
        ROLLBACK TRANSACTION;

    INSERT INTO #StageAudit
    (AuditAction, AffectedEntity, ReferenceId, AuditPayload)
VALUES
    (
        N'ERROR',
        N'PROCESSING',
        CONVERT(NVARCHAR(128), ERROR_NUMBER()),
        CONCAT(
            N'{"message":"', REPLACE(ERROR_MESSAGE(), '"', '\"'),
            N'","line":', ERROR_LINE(),
            N',"procedure":"', COALESCE(ERROR_PROCEDURE(), N''), N'"}'
        )
    );

    THROW;
END CATCH;

;WITH
    RankedAudit
    AS
    (
        SELECT
            a.AuditId,
            a.AuditUtc,
            a.AuditAction,
            a.AffectedEntity,
            a.ReferenceId,
            a.AuditPayload,
            ROW_NUMBER() OVER (
            PARTITION BY a.AuditAction
            ORDER BY a.AuditUtc DESC, a.AuditId DESC
        ) AS ActionRank
        FROM #StageAudit a
    )
SELECT
    ra.AuditId,
    ra.AuditUtc,
    ra.AuditAction,
    ra.AffectedEntity,
    ra.ReferenceId,
    ra.AuditPayload
FROM RankedAudit ra
WHERE ra.ActionRank <= 5
ORDER BY ra.AuditUtc DESC, ra.AuditId DESC;

DROP TABLE IF EXISTS #UnpivotedStatusAmounts;
DROP TABLE IF EXISTS #PivotedOrderStatusAmounts;
DROP TABLE IF EXISTS #CustomerOperationalSnapshot;
DROP TABLE IF EXISTS #StageAudit;
DROP TABLE IF EXISTS #StageOrders;
GO


GO
