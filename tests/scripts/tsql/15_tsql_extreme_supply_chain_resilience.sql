-- Extreme T-SQL stress sample 3
-- Purpose: supply-chain resilience workflow with temporal staging, savepoints,
-- queue-style updates, recursive graph traversal, service-level breach detection,
-- JSON/XML packaging, dynamic SQL, and procedural exception handling.

SET NOCOUNT ON;
SET XACT_ABORT ON;
SET DEADLOCK_PRIORITY LOW;

DROP TABLE IF EXISTS #InboundShipmentStage;
DROP TABLE IF EXISTS #SupplierRiskAlerts;
DROP TABLE IF EXISTS #NodeTraversal;
DROP TABLE IF EXISTS #BreachMatrix;

CREATE TABLE #InboundShipmentStage
(
    ShipmentStageId BIGINT IDENTITY(1, 1) PRIMARY KEY,
    ShipmentBatchId UNIQUEIDENTIFIER NOT NULL DEFAULT NEWID(),
    ShipmentNumber NVARCHAR(40) NOT NULL,
    ParentShipmentNumber NVARCHAR(40) NULL,
    PurchaseOrderNumber NVARCHAR(40) NOT NULL,
    SupplierCode NVARCHAR(30) NOT NULL,
    OriginPortCode NVARCHAR(10) NOT NULL,
    DestinationNodeCode NVARCHAR(20) NOT NULL,
    TransportModeCode NVARCHAR(20) NOT NULL,
    IncotermCode NVARCHAR(10) NOT NULL,
    MaterialCode NVARCHAR(40) NOT NULL,
    MaterialFamilyCode NVARCHAR(30) NOT NULL,
    RegulatoryRegionCode NVARCHAR(20) NOT NULL,
    RequiredDeliveryDate DATE NOT NULL,
    EstimatedArrivalUtc DATETIME2(3) NULL,
    ActualArrivalUtc DATETIME2(3) NULL,
    PlannedQuantity DECIMAL(19, 4) NOT NULL,
    ConfirmedQuantity DECIMAL(19, 4) NOT NULL,
    ReceivedQuantity DECIMAL(19, 4) NOT NULL,
    UnitCost DECIMAL(19, 6) NOT NULL,
    CurrencyCode CHAR(3) NOT NULL,
    DelayMinutes INT NULL,
    TemperatureCelsius DECIMAL(9, 3) NULL,
    ShockEventCount INT NOT NULL DEFAULT 0,
    IsColdChain BIT NOT NULL,
    PayloadJson NVARCHAR(MAX) NULL,
    ExceptionXml XML NULL,
    IngestedUtc DATETIME2(3) NOT NULL DEFAULT SYSUTCDATETIME(),
    FunctionalValue AS (ConfirmedQuantity * UnitCost) PERSISTED
);

CREATE TABLE #SupplierRiskAlerts
(
    AlertId BIGINT IDENTITY(1, 1) PRIMARY KEY,
    AlertUtc DATETIME2(3) NOT NULL DEFAULT SYSUTCDATETIME(),
    AlertCategory NVARCHAR(50) NOT NULL,
    SeverityCode NVARCHAR(20) NOT NULL,
    SupplierCode NVARCHAR(30) NULL,
    ShipmentNumber NVARCHAR(40) NULL,
    PurchaseOrderNumber NVARCHAR(40) NULL,
    MaterialCode NVARCHAR(40) NULL,
    AlertMessage NVARCHAR(4000) NOT NULL,
    DiagnosticJson NVARCHAR(MAX) NULL
);

DECLARE @SupplierMaster TABLE
(
    SupplierCode NVARCHAR(30) PRIMARY KEY,
    SupplierTier NVARCHAR(10) NOT NULL,
    CriticalityScore INT NOT NULL,
    CountryCode CHAR(2) NOT NULL,
    DualSourceFlag BIT NOT NULL,
    SupplierPayload NVARCHAR(MAX) NULL
);

DECLARE @RouteNetwork TABLE
(
    FromNodeCode NVARCHAR(20) NOT NULL,
    ToNodeCode NVARCHAR(20) NOT NULL,
    TransitModeCode NVARCHAR(20) NOT NULL,
    NominalTransitHours INT NOT NULL,
    RouteRiskScore INT NOT NULL,
    PRIMARY KEY (FromNodeCode, ToNodeCode, TransitModeCode)
);

DECLARE @InboundFeed TABLE
(
    FeedRowId INT IDENTITY(1, 1) PRIMARY KEY,
    ShipmentNumber NVARCHAR(40) NOT NULL,
    ParentShipmentNumber NVARCHAR(40) NULL,
    PurchaseOrderNumber NVARCHAR(40) NOT NULL,
    SupplierCode NVARCHAR(30) NOT NULL,
    OriginPortCode NVARCHAR(10) NOT NULL,
    DestinationNodeCode NVARCHAR(20) NOT NULL,
    TransportModeCode NVARCHAR(20) NOT NULL,
    IncotermCode NVARCHAR(10) NOT NULL,
    MaterialCode NVARCHAR(40) NOT NULL,
    MaterialFamilyCode NVARCHAR(30) NOT NULL,
    RegulatoryRegionCode NVARCHAR(20) NOT NULL,
    RequiredDeliveryDate DATE NOT NULL,
    EstimatedArrivalUtc DATETIME2(3) NULL,
    ActualArrivalUtc DATETIME2(3) NULL,
    PlannedQuantity DECIMAL(19, 4) NOT NULL,
    ConfirmedQuantity DECIMAL(19, 4) NOT NULL,
    ReceivedQuantity DECIMAL(19, 4) NOT NULL,
    UnitCost DECIMAL(19, 6) NOT NULL,
    CurrencyCode CHAR(3) NOT NULL,
    DelayMinutes INT NULL,
    TemperatureCelsius DECIMAL(9, 3) NULL,
    ShockEventCount INT NOT NULL,
    IsColdChain BIT NOT NULL,
    PayloadJson NVARCHAR(MAX) NULL,
    ExceptionXml XML NULL
);

INSERT INTO @SupplierMaster
(
    SupplierCode,
    SupplierTier,
    CriticalityScore,
    CountryCode,
    DualSourceFlag,
    SupplierPayload
)
VALUES
    (N'SUP-ALPHA', N'T1', 97, N'US', 0, N'{"owner":"NorthAmerica","watchlist":["capacity"],"esg":"amber"}'),
    (N'SUP-BETA', N'T2', 72, N'DE', 1, N'{"owner":"Europe","watchlist":["freight"],"esg":"green"}'),
    (N'SUP-GAMMA', N'T1', 91, N'JP', 0, N'{"owner":"Asia","watchlist":["geopolitical","quality"],"esg":"amber"}'),
    (N'SUP-OMEGA', N'T3', 54, N'BR', 1, N'{"owner":"LATAM","watchlist":[],"esg":"green"}');

INSERT INTO @RouteNetwork
(
    FromNodeCode,
    ToNodeCode,
    TransitModeCode,
    NominalTransitHours,
    RouteRiskScore
)
VALUES
    (N'SHANGHAI', N'ROTTERDAM', N'OCEAN', 420, 74),
    (N'ROTTERDAM', N'AMS-DC', N'TRUCK', 8, 12),
    (N'NAGOYA', N'LAX', N'AIR', 16, 38),
    (N'LAX', N'PHX-DC', N'TRUCK', 11, 17),
    (N'SANTOS', N'MIA', N'OCEAN', 240, 42),
    (N'MIA', N'ATL-DC', N'TRUCK', 14, 15),
    (N'HAMBURG', N'PRG-HUB', N'RAIL', 18, 22);

INSERT INTO @InboundFeed
(
    ShipmentNumber,
    ParentShipmentNumber,
    PurchaseOrderNumber,
    SupplierCode,
    OriginPortCode,
    DestinationNodeCode,
    TransportModeCode,
    IncotermCode,
    MaterialCode,
    MaterialFamilyCode,
    RegulatoryRegionCode,
    RequiredDeliveryDate,
    EstimatedArrivalUtc,
    ActualArrivalUtc,
    PlannedQuantity,
    ConfirmedQuantity,
    ReceivedQuantity,
    UnitCost,
    CurrencyCode,
    DelayMinutes,
    TemperatureCelsius,
    ShockEventCount,
    IsColdChain,
    PayloadJson,
    ExceptionXml
)
VALUES
    (
        N'SHP-100001',
        NULL,
        N'PO-780001',
        N'SUP-ALPHA',
        N'LAX',
        N'PHX-DC',
        N'TRUCK',
        N'DDP',
        N'MAT-THERMAL-01',
        N'COLD_CHAIN',
        N'US-FDA',
        '2025-12-02',
        '2025-12-01T10:00:00',
        NULL,
        1800.0000,
        1750.0000,
        0.0000,
        42.750000,
        N'USD',
        185,
        9.250,
        3,
        1,
        N'{"priority":"expedite","handoffs":["dock","crossdock"],"resilience":{"bufferDays":1,"insurance":"enhanced"}}',
        '<exceptions><event code="TEMP_SPIKE" severity="HIGH" /><event code="LATE_GATE_IN" severity="MEDIUM" /></exceptions>'
    ),
    (
        N'SHP-100002',
        N'SHP-100001',
        N'PO-780001',
        N'SUP-ALPHA',
        N'LAX',
        N'PHX-DC',
        N'TRUCK',
        N'DDP',
        N'MAT-THERMAL-01',
        N'COLD_CHAIN',
        N'US-FDA',
        '2025-12-02',
        '2025-12-01T14:00:00',
        NULL,
        200.0000,
        200.0000,
        0.0000,
        42.750000,
        N'USD',
        30,
        6.400,
        0,
        1,
        N'{"priority":"expedite","splitReason":"capacity","resilience":{"bufferDays":1,"insurance":"enhanced"}}',
        '<exceptions />'
    ),
    (
        N'SHP-200001',
        NULL,
        N'PO-880110',
        N'SUP-GAMMA',
        N'NAGOYA',
        N'LAX',
        N'AIR',
        N'CIP',
        N'MAT-ROBOT-09',
        N'AUTOMATION',
        N'US-UL',
        '2025-12-05',
        '2025-12-04T04:30:00',
        NULL,
        24.0000,
        24.0000,
        0.0000,
        18500.000000,
        N'USD',
        0,
        NULL,
        1,
        0,
        N'{"priority":"critical","handoffs":["secure-cage"],"resilience":{"bufferDays":0,"insurance":"premium"}}',
        '<exceptions><event code="SHOCK_ALERT" severity="HIGH" /></exceptions>'
    ),
    (
        N'SHP-300001',
        NULL,
        N'PO-441920',
        N'SUP-BETA',
        N'ROTTERDAM',
        N'AMS-DC',
        N'TRUCK',
        N'DAP',
        N'MAT-PACK-77',
        N'PACKAGING',
        N'EU-REACH',
        '2025-12-01',
        '2025-11-30T07:00:00',
        '2025-11-30T06:45:00',
        42000.0000,
        42000.0000,
        41880.0000,
        0.920000,
        N'EUR',
        -15,
        NULL,
        0,
        0,
        N'{"priority":"standard","handoffs":["dock"],"resilience":{"bufferDays":4,"insurance":"basic"}}',
        '<exceptions />'
    ),
    (
        N'SHP-400001',
        NULL,
        N'PO-551001',
        N'SUP-OMEGA',
        N'SANTOS',
        N'MIA',
        N'OCEAN',
        N'FOB',
        N'MAT-RESIN-03',
        N'RAW_MATERIAL',
        N'US-EPA',
        '2025-12-10',
        '2025-12-14T18:00:00',
        NULL,
        99000.0000,
        97000.0000,
        0.0000,
        1.430000,
        N'USD',
        5760,
        NULL,
        0,
        0,
        N'{"priority":"standard","handoffs":["port","drayage"],"resilience":{"bufferDays":2,"insurance":"basic"}}',
        '<exceptions><event code="PORT_CONGESTION" severity="HIGH" /></exceptions>'
    );

INSERT INTO #InboundShipmentStage
(
    ShipmentNumber,
    ParentShipmentNumber,
    PurchaseOrderNumber,
    SupplierCode,
    OriginPortCode,
    DestinationNodeCode,
    TransportModeCode,
    IncotermCode,
    MaterialCode,
    MaterialFamilyCode,
    RegulatoryRegionCode,
    RequiredDeliveryDate,
    EstimatedArrivalUtc,
    ActualArrivalUtc,
    PlannedQuantity,
    ConfirmedQuantity,
    ReceivedQuantity,
    UnitCost,
    CurrencyCode,
    DelayMinutes,
    TemperatureCelsius,
    ShockEventCount,
    IsColdChain,
    PayloadJson,
    ExceptionXml
)
SELECT
    f.ShipmentNumber,
    f.ParentShipmentNumber,
    f.PurchaseOrderNumber,
    f.SupplierCode,
    f.OriginPortCode,
    f.DestinationNodeCode,
    f.TransportModeCode,
    f.IncotermCode,
    f.MaterialCode,
    f.MaterialFamilyCode,
    f.RegulatoryRegionCode,
    f.RequiredDeliveryDate,
    f.EstimatedArrivalUtc,
    f.ActualArrivalUtc,
    f.PlannedQuantity,
    f.ConfirmedQuantity,
    f.ReceivedQuantity,
    f.UnitCost,
    f.CurrencyCode,
    f.DelayMinutes,
    f.TemperatureCelsius,
    f.ShockEventCount,
    f.IsColdChain,
    f.PayloadJson,
    f.ExceptionXml
FROM @InboundFeed f;

BEGIN TRY
    BEGIN TRANSACTION;
    SAVE TRANSACTION BeforeRiskEvaluation;

    ;WITH ShipmentHierarchy AS
    (
        SELECT
            s.ShipmentStageId,
            s.ShipmentNumber,
            s.ParentShipmentNumber,
            CAST(s.ShipmentNumber AS NVARCHAR(4000)) AS ShipmentPath,
            0 AS Depth
        FROM #InboundShipmentStage s
        WHERE s.ParentShipmentNumber IS NULL

        UNION ALL

        SELECT
            c.ShipmentStageId,
            c.ShipmentNumber,
            c.ParentShipmentNumber,
            CAST(h.ShipmentPath + N'>' + c.ShipmentNumber AS NVARCHAR(4000)),
            h.Depth + 1
        FROM #InboundShipmentStage c
        INNER JOIN ShipmentHierarchy h
            ON c.ParentShipmentNumber = h.ShipmentNumber
    ),
    Enriched AS
    (
        SELECT
            s.ShipmentStageId,
            s.ShipmentNumber,
            s.ParentShipmentNumber,
            s.PurchaseOrderNumber,
            s.SupplierCode,
            sm.SupplierTier,
            sm.CriticalityScore,
            sm.DualSourceFlag,
            s.OriginPortCode,
            s.DestinationNodeCode,
            s.TransportModeCode,
            s.MaterialCode,
            s.MaterialFamilyCode,
            s.RegulatoryRegionCode,
            s.RequiredDeliveryDate,
            s.EstimatedArrivalUtc,
            s.ActualArrivalUtc,
            s.PlannedQuantity,
            s.ConfirmedQuantity,
            s.ReceivedQuantity,
            s.UnitCost,
            s.FunctionalValue,
            s.DelayMinutes,
            s.TemperatureCelsius,
            s.ShockEventCount,
            s.IsColdChain,
            sh.ShipmentPath,
            sh.Depth,
            JSON_VALUE(s.PayloadJson, '$.priority') AS ShipmentPriority,
            TRY_CAST(JSON_VALUE(s.PayloadJson, '$.resilience.bufferDays') AS INT) AS BufferDays,
            JSON_VALUE(s.PayloadJson, '$.resilience.insurance') AS InsuranceTier,
            DATEDIFF(MINUTE, SYSUTCDATETIME(), s.EstimatedArrivalUtc) AS MinutesToEta,
            SUM(s.FunctionalValue) OVER (PARTITION BY s.SupplierCode) AS SupplierOpenExposure,
            MAX(s.DelayMinutes) OVER (PARTITION BY s.SupplierCode, s.MaterialFamilyCode) AS WorstDelayByFamily
        FROM #InboundShipmentStage s
        INNER JOIN @SupplierMaster sm
            ON sm.SupplierCode = s.SupplierCode
        INNER JOIN ShipmentHierarchy sh
            ON sh.ShipmentStageId = s.ShipmentStageId
    ),
    BreachProjection AS
    (
        SELECT
            e.ShipmentStageId,
            e.ShipmentNumber,
            e.SupplierCode,
            e.PurchaseOrderNumber,
            e.MaterialCode,
            e.MaterialFamilyCode,
            e.ShipmentPriority,
            e.BufferDays,
            e.InsuranceTier,
            e.SupplierTier,
            e.CriticalityScore,
            e.SupplierOpenExposure,
            e.DelayMinutes,
            e.ShockEventCount,
            e.IsColdChain,
            e.RequiredDeliveryDate,
            CASE
                WHEN e.EstimatedArrivalUtc IS NULL THEN N'ETA_UNKNOWN'
                WHEN CAST(e.EstimatedArrivalUtc AS DATE) > DATEADD(DAY, ISNULL(e.BufferDays, 0), e.RequiredDeliveryDate) THEN N'SLA_BREACH'
                WHEN e.DelayMinutes >= 720 THEN N'SEVERE_DELAY'
                WHEN e.IsColdChain = 1 AND e.TemperatureCelsius > 8.000 THEN N'COLD_CHAIN_EXCURSION'
                WHEN e.ShockEventCount >= 1 AND e.MaterialFamilyCode = N'AUTOMATION' THEN N'SHOCK_IMPACT'
                ELSE N'OK'
            END AS BreachState
        FROM Enriched e
    )
    INSERT INTO #SupplierRiskAlerts
    (
        AlertCategory,
        SeverityCode,
        SupplierCode,
        ShipmentNumber,
        PurchaseOrderNumber,
        MaterialCode,
        AlertMessage,
        DiagnosticJson
    )
    SELECT
        N'RESILIENCE_BREACH',
        CASE
            WHEN bp.BreachState IN (N'COLD_CHAIN_EXCURSION', N'SHOCK_IMPACT') THEN N'CRITICAL'
            WHEN bp.BreachState = N'SLA_BREACH' AND bp.CriticalityScore >= 90 THEN N'CRITICAL'
            WHEN bp.BreachState IN (N'SLA_BREACH', N'SEVERE_DELAY') THEN N'HIGH'
            ELSE N'MEDIUM'
        END,
        bp.SupplierCode,
        bp.ShipmentNumber,
        bp.PurchaseOrderNumber,
        bp.MaterialCode,
        CONCAT(N'Shipment breach state detected: ', bp.BreachState),
        CONCAT(
            N'{"supplierTier":"', bp.SupplierTier,
            N'","priority":"', COALESCE(bp.ShipmentPriority, N''),
            N'","bufferDays":', COALESCE(CONVERT(NVARCHAR(20), bp.BufferDays), N'null'),
            N',"exposure":', CONVERT(NVARCHAR(50), bp.SupplierOpenExposure),
            N',"delayMinutes":', COALESCE(CONVERT(NVARCHAR(20), bp.DelayMinutes), N'null'),
            N',"shockEventCount":', bp.ShockEventCount,
            N'}'
        )
    FROM BreachProjection bp
    WHERE bp.BreachState <> N'OK';

    CREATE TABLE #NodeTraversal
    (
        TraversalId BIGINT IDENTITY(1, 1) PRIMARY KEY,
        ShipmentNumber NVARCHAR(40) NOT NULL,
        FromNodeCode NVARCHAR(20) NOT NULL,
        ToNodeCode NVARCHAR(20) NOT NULL,
        TransitModeCode NVARCHAR(20) NOT NULL,
        NominalTransitHours INT NOT NULL,
        RouteRiskScore INT NOT NULL,
        TraversalDepth INT NOT NULL,
        TraversalPath NVARCHAR(4000) NOT NULL
    );

    ;WITH RecursiveNetwork AS
    (
        SELECT
            s.ShipmentNumber,
            s.OriginPortCode AS FromNodeCode,
            s.DestinationNodeCode AS ToNodeCode,
            s.TransportModeCode AS TransitModeCode,
            0 AS TraversalDepth,
            CAST(s.OriginPortCode + N'>' + s.DestinationNodeCode AS NVARCHAR(4000)) AS TraversalPath
        FROM #InboundShipmentStage s

        UNION ALL

        SELECT
            rn.ShipmentNumber,
            net.FromNodeCode,
            net.ToNodeCode,
            net.TransitModeCode,
            rn.TraversalDepth + 1,
            CAST(rn.TraversalPath + N'>' + net.ToNodeCode AS NVARCHAR(4000))
        FROM RecursiveNetwork rn
        INNER JOIN @RouteNetwork net
            ON rn.ToNodeCode = net.FromNodeCode
        WHERE rn.TraversalDepth < 4
    )
    INSERT INTO #NodeTraversal
    (
        ShipmentNumber,
        FromNodeCode,
        ToNodeCode,
        TransitModeCode,
        NominalTransitHours,
        RouteRiskScore,
        TraversalDepth,
        TraversalPath
    )
    SELECT
        rn.ShipmentNumber,
        rn.FromNodeCode,
        rn.ToNodeCode,
        rn.TransitModeCode,
        ISNULL(net.NominalTransitHours, 0),
        ISNULL(net.RouteRiskScore, 0),
        rn.TraversalDepth,
        rn.TraversalPath
    FROM RecursiveNetwork rn
    LEFT JOIN @RouteNetwork net
        ON rn.FromNodeCode = net.FromNodeCode
       AND rn.ToNodeCode = net.ToNodeCode
       AND rn.TransitModeCode = net.TransitModeCode
    OPTION (MAXRECURSION 100);

    SELECT
        s.SupplierCode,
        s.MaterialFamilyCode,
        COUNT(*) AS ShipmentCount,
        SUM(s.FunctionalValue) AS SupplierExposure,
        MAX(COALESCE(s.DelayMinutes, 0)) AS MaxDelayMinutes,
        SUM(CASE WHEN a.SeverityCode = N'CRITICAL' THEN 1 ELSE 0 END) AS CriticalAlertCount,
        STRING_AGG(DISTINCT s.TransportModeCode, N',') WITHIN GROUP (ORDER BY s.TransportModeCode) AS ModesObserved
    INTO #BreachMatrix
    FROM #InboundShipmentStage s
    LEFT JOIN #SupplierRiskAlerts a
        ON a.ShipmentNumber = s.ShipmentNumber
    GROUP BY
        s.SupplierCode,
        s.MaterialFamilyCode;

    DECLARE @DynamicColumns NVARCHAR(MAX);
    DECLARE @DynamicMatrixSql NVARCHAR(MAX);

    SELECT
        @DynamicColumns = STRING_AGG(QUOTENAME(MaterialFamilyCode), N',')
    FROM
    (
        SELECT DISTINCT MaterialFamilyCode
        FROM #InboundShipmentStage
    ) d;

    SET @DynamicMatrixSql = N'
        SELECT SupplierCode, ' + @DynamicColumns + N'
        INTO #SupplierExposurePivot
        FROM
        (
            SELECT SupplierCode, MaterialFamilyCode, FunctionalValue
            FROM #InboundShipmentStage
        ) src
        PIVOT
        (
            SUM(FunctionalValue)
            FOR MaterialFamilyCode IN (' + @DynamicColumns + N')
        ) p;';

    EXEC sys.sp_executesql @DynamicMatrixSql;

    MERGE dbo.SupplierResilienceSnapshot AS target
    USING
    (
        SELECT
            bm.SupplierCode,
            bm.MaterialFamilyCode,
            bm.ShipmentCount,
            bm.SupplierExposure,
            bm.MaxDelayMinutes,
            bm.CriticalAlertCount,
            bm.ModesObserved,
            SYSUTCDATETIME() AS SnapshotUtc
        FROM #BreachMatrix bm
    ) AS source
        ON target.SupplierCode = source.SupplierCode
       AND target.MaterialFamilyCode = source.MaterialFamilyCode
    WHEN MATCHED THEN
        UPDATE SET
            target.ActiveShipmentCount = source.ShipmentCount,
            target.OpenExposure = source.SupplierExposure,
            target.MaxDelayMinutes = source.MaxDelayMinutes,
            target.CriticalAlertCount = source.CriticalAlertCount,
            target.TransportModes = source.ModesObserved,
            target.LastRefreshUtc = source.SnapshotUtc
    WHEN NOT MATCHED THEN
        INSERT
        (
            SupplierCode,
            MaterialFamilyCode,
            ActiveShipmentCount,
            OpenExposure,
            MaxDelayMinutes,
            CriticalAlertCount,
            TransportModes,
            LastRefreshUtc
        )
        VALUES
        (
            source.SupplierCode,
            source.MaterialFamilyCode,
            source.ShipmentCount,
            source.SupplierExposure,
            source.MaxDelayMinutes,
            source.CriticalAlertCount,
            source.ModesObserved,
            source.SnapshotUtc
        )
    OUTPUT
        $action,
        inserted.SupplierCode,
        inserted.MaterialFamilyCode,
        inserted.LastRefreshUtc
    INTO dbo.SupplierResilienceAudit
    (
        MergeAction,
        SupplierCode,
        MaterialFamilyCode,
        AuditUtc
    );

    IF EXISTS
    (
        SELECT 1
        FROM #SupplierRiskAlerts
        WHERE SeverityCode = N'CRITICAL'
    )
    BEGIN
        WAITFOR DELAY '00:00:02';
    END;

    DECLARE @AlertCursorSupplierCode NVARCHAR(30);
    DECLARE @AlertCursorShipmentNumber NVARCHAR(40);
    DECLARE @AlertCursorSeverityCode NVARCHAR(20);

    DECLARE AlertDispatchCursor CURSOR LOCAL FAST_FORWARD FOR
        SELECT
            a.SupplierCode,
            a.ShipmentNumber,
            a.SeverityCode
        FROM #SupplierRiskAlerts a
        WHERE a.SeverityCode IN (N'CRITICAL', N'HIGH')
        ORDER BY a.AlertUtc, a.AlertId;

    OPEN AlertDispatchCursor;
    FETCH NEXT FROM AlertDispatchCursor INTO @AlertCursorSupplierCode, @AlertCursorShipmentNumber, @AlertCursorSeverityCode;

    WHILE @@FETCH_STATUS = 0
    BEGIN
        EXEC dbo.usp_DispatchSupplierResilienceAlert
            @SupplierCode = @AlertCursorSupplierCode,
            @ShipmentNumber = @AlertCursorShipmentNumber,
            @SeverityCode = @AlertCursorSeverityCode,
            @RequestedUtc = SYSUTCDATETIME();

        FETCH NEXT FROM AlertDispatchCursor INTO @AlertCursorSupplierCode, @AlertCursorShipmentNumber, @AlertCursorSeverityCode;
    END;

    CLOSE AlertDispatchCursor;
    DEALLOCATE AlertDispatchCursor;

    INSERT INTO dbo.ResilienceRunLog
    (
        RunUtc,
        RunType,
        StatusCode,
        SummaryJson,
        SummaryXml
    )
    SELECT
        SYSUTCDATETIME(),
        N'SUPPLY_CHAIN_RESILIENCE',
        CASE
            WHEN EXISTS (SELECT 1 FROM #SupplierRiskAlerts WHERE SeverityCode = N'CRITICAL') THEN N'ESCALATED'
            WHEN EXISTS (SELECT 1 FROM #SupplierRiskAlerts) THEN N'WARNINGS'
            ELSE N'CLEAR'
        END,
        (
            SELECT
                a.AlertCategory,
                a.SeverityCode,
                a.SupplierCode,
                a.ShipmentNumber,
                a.MaterialCode,
                a.AlertMessage
            FROM #SupplierRiskAlerts a
            FOR JSON PATH, INCLUDE_NULL_VALUES
        ),
        (
            SELECT
                nt.ShipmentNumber AS [@shipment],
                nt.FromNodeCode AS [fromNode],
                nt.ToNodeCode AS [toNode],
                nt.TransitModeCode AS [mode],
                nt.RouteRiskScore AS [routeRisk]
            FROM #NodeTraversal nt
            FOR XML PATH('edge'), ROOT('network'), TYPE
        );

    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    IF CURSOR_STATUS('local', 'AlertDispatchCursor') >= -1
    BEGIN
        CLOSE AlertDispatchCursor;
        DEALLOCATE AlertDispatchCursor;
    END;

    IF XACT_STATE() = -1
        ROLLBACK TRANSACTION;
    ELSE IF XACT_STATE() = 1
        ROLLBACK TRANSACTION BeforeRiskEvaluation;

    INSERT INTO #SupplierRiskAlerts
    (
        AlertCategory,
        SeverityCode,
        SupplierCode,
        ShipmentNumber,
        PurchaseOrderNumber,
        MaterialCode,
        AlertMessage,
        DiagnosticJson
    )
    VALUES
    (
        N'RUNTIME_FAILURE',
        N'CRITICAL',
        NULL,
        NULL,
        NULL,
        NULL,
        ERROR_MESSAGE(),
        CONCAT(
            N'{"errorNumber":', ERROR_NUMBER(),
            N',"errorLine":', ERROR_LINE(),
            N',"errorState":', ERROR_STATE(),
            N',"procedure":"', COALESCE(ERROR_PROCEDURE(), N''), N'"}'
        )
    );

    THROW;
END CATCH;

SELECT
    a.AlertId,
    a.AlertUtc,
    a.AlertCategory,
    a.SeverityCode,
    a.SupplierCode,
    a.ShipmentNumber,
    a.PurchaseOrderNumber,
    a.MaterialCode,
    a.AlertMessage,
    a.DiagnosticJson
FROM #SupplierRiskAlerts a
ORDER BY
    CASE a.SeverityCode
        WHEN N'CRITICAL' THEN 1
        WHEN N'HIGH' THEN 2
        WHEN N'MEDIUM' THEN 3
        ELSE 4
    END,
    a.AlertUtc DESC,
    a.AlertId DESC;

SELECT
    nt.ShipmentNumber,
    nt.FromNodeCode,
    nt.ToNodeCode,
    nt.TransitModeCode,
    nt.RouteRiskScore,
    nt.TraversalDepth,
    nt.TraversalPath
FROM #NodeTraversal nt
ORDER BY
    nt.ShipmentNumber,
    nt.TraversalDepth,
    nt.TraversalId;

DROP TABLE IF EXISTS #BreachMatrix;
DROP TABLE IF EXISTS #NodeTraversal;
DROP TABLE IF EXISTS #SupplierExposurePivot;
DROP TABLE IF EXISTS #SupplierRiskAlerts;
DROP TABLE IF EXISTS #InboundShipmentStage;
GO

EXEC dbo.usp_FinalizeSupplyChainResilienceWindow
    @WindowCode = N'GLOBAL_SUPPLY_RESILIENCE',
    @ClosedUtc = SYSUTCDATETIME(),
    @ClosedBy = ORIGINAL_LOGIN();
