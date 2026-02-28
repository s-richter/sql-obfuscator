/* Extreme T-SQL stress sample 5 */
/* Purpose: grid balancing workflow with recursive feeder topology, */
/* reserve shortfall detection, dispatch queueing, dynamic interval pivots, */
/* JSON/XML packaging, savepoints, cursor-driven notifications, and recovery logic. */

SET NOCOUNT ON;
SET XACT_ABORT ON;
SET DEADLOCK_PRIORITY HIGH;

DROP TABLE IF EXISTS #GridTelemetryStage;
DROP TABLE IF EXISTS #ReserveAlertQueue;
DROP TABLE IF EXISTS #FeederTopology;
DROP TABLE IF EXISTS #IntervalPivotSeed;

CREATE TABLE #GridTelemetryStage
(
    StageTelemetryId BIGINT IDENTITY(1, 1) PRIMARY KEY,
    LoadBatchId UNIQUEIDENTIFIER NOT NULL DEFAULT NEWID(),
    MarketCode NVARCHAR(20) NOT NULL,
    ControlAreaCode NVARCHAR(20) NOT NULL,
    RegionCode NVARCHAR(20) NOT NULL,
    ParentNodeCode NVARCHAR(30) NULL,
    NodeCode NVARCHAR(30) NOT NULL,
    FeederCode NVARCHAR(30) NOT NULL,
    ResourceCode NVARCHAR(30) NOT NULL,
    ResourceTypeCode NVARCHAR(20) NOT NULL,
    DispatchModeCode NVARCHAR(20) NOT NULL,
    IntervalCode NVARCHAR(20) NOT NULL,
    TelemetryUtc DATETIME2(3) NOT NULL,
    IntervalStartUtc DATETIME2(3) NOT NULL,
    IntervalEndUtc DATETIME2(3) NOT NULL,
    ScheduledMw NUMERIC(19, 4) NOT NULL,
    ActualMw NUMERIC(19, 4) NOT NULL,
    ReserveMw NUMERIC(19, 4) NOT NULL,
    ReserveRequirementMw NUMERIC(19, 4) NOT NULL,
    FrequencyHz NUMERIC(9, 4) NULL,
    VoltageKv NUMERIC(19, 4) NULL,
    CongestionIndex NUMERIC(19, 4) NULL,
    CurtailmentMw NUMERIC(19, 4) NOT NULL,
    ImbalanceMw AS (ActualMw - ScheduledMw) PERSISTED,
    TelemetryJson NVARCHAR(MAX) NULL,
    DiagnosticXml XML NULL,
    CreatedUtc DATETIME2(3) NOT NULL DEFAULT SYSUTCDATETIME()
);

CREATE TABLE #ReserveAlertQueue
(
    AlertId BIGINT IDENTITY(1, 1) PRIMARY KEY,
    AlertUtc DATETIME2(3) NOT NULL DEFAULT SYSUTCDATETIME(),
    AlertCategory NVARCHAR(40) NOT NULL,
    SeverityCode NVARCHAR(20) NOT NULL,
    MarketCode NVARCHAR(20) NULL,
    ControlAreaCode NVARCHAR(20) NULL,
    NodeCode NVARCHAR(30) NULL,
    ResourceCode NVARCHAR(30) NULL,
    AlertMessage NVARCHAR(4000) NOT NULL,
    AlertPayload NVARCHAR(MAX) NULL
);

CREATE TABLE #FeederTopology
(
    TopologyRowId BIGINT IDENTITY(1, 1) PRIMARY KEY,
    NodeCode NVARCHAR(30) NOT NULL,
    ParentNodeCode NVARCHAR(30) NULL,
    TopologyLevel INTEGER NOT NULL,
    TopologyPath NVARCHAR(4000) NOT NULL
);

CREATE TABLE #IntervalPivotSeed
(
    MarketCode NVARCHAR(20) NOT NULL,
    ControlAreaCode NVARCHAR(20) NOT NULL,
    IntervalCode NVARCHAR(20) NOT NULL,
    FunctionalMw NUMERIC(19, 4) NOT NULL
);

DECLARE @MarketProfile TABLE
(
    MarketCode NVARCHAR(20) PRIMARY KEY,
    ReservePolicyCode NVARCHAR(20) NOT NULL,
    CriticalFrequencyFloor NUMERIC(9, 4) NOT NULL,
    MaxCongestionIndex NUMERIC(19, 4) NOT NULL,
    MarketProfileJson NVARCHAR(MAX) NULL
);

DECLARE @TransmissionEdges TABLE
(
    ParentNodeCode NVARCHAR(30) NOT NULL,
    ChildNodeCode NVARCHAR(30) NOT NULL,
    TransferLimitMw NUMERIC(19, 4) NOT NULL,
    EffectiveUtc DATETIME2(3) NOT NULL,
    PRIMARY KEY (ParentNodeCode, ChildNodeCode, EffectiveUtc)
);

DECLARE @InboundTelemetry TABLE
(
    FeedRowId INTEGER IDENTITY(1, 1) PRIMARY KEY,
    MarketCode NVARCHAR(20) NOT NULL,
    ControlAreaCode NVARCHAR(20) NOT NULL,
    RegionCode NVARCHAR(20) NOT NULL,
    ParentNodeCode NVARCHAR(30) NULL,
    NodeCode NVARCHAR(30) NOT NULL,
    FeederCode NVARCHAR(30) NOT NULL,
    ResourceCode NVARCHAR(30) NOT NULL,
    ResourceTypeCode NVARCHAR(20) NOT NULL,
    DispatchModeCode NVARCHAR(20) NOT NULL,
    IntervalCode NVARCHAR(20) NOT NULL,
    TelemetryUtc DATETIME2(3) NOT NULL,
    IntervalStartUtc DATETIME2(3) NOT NULL,
    IntervalEndUtc DATETIME2(3) NOT NULL,
    ScheduledMw NUMERIC(19, 4) NOT NULL,
    ActualMw NUMERIC(19, 4) NOT NULL,
    ReserveMw NUMERIC(19, 4) NOT NULL,
    ReserveRequirementMw NUMERIC(19, 4) NOT NULL,
    FrequencyHz NUMERIC(9, 4) NULL,
    VoltageKv NUMERIC(19, 4) NULL,
    CongestionIndex NUMERIC(19, 4) NULL,
    CurtailmentMw NUMERIC(19, 4) NOT NULL,
    TelemetryJson NVARCHAR(MAX) NULL,
    DiagnosticXml XML NULL
);

INSERT INTO @MarketProfile
(
    MarketCode,
    ReservePolicyCode,
    CriticalFrequencyFloor,
    MaxCongestionIndex,
    MarketProfileJson
)
VALUES
    (N'NORDPOOL', N'PRIMARY', 49.8500, 6.5000, N'{"operator":"north-grid","reserveFloorPct":12,"priority":"hydro"}'),
    (N'ERCOT', N'CONTINGENCY', 59.9200, 8.2000, N'{"operator":"south-grid","reserveFloorPct":10,"priority":"gas"}'),
    (N'PJM', N'SYNCHRONIZED', 59.9400, 7.3000, N'{"operator":"east-grid","reserveFloorPct":11,"priority":"storage"}');

INSERT INTO @TransmissionEdges
(
    ParentNodeCode,
    ChildNodeCode,
    TransferLimitMw,
    EffectiveUtc
)
VALUES
    (N'N-SE-HUB', N'N-SE-LOAD-01', 850.0000, '2025-01-01T00:00:00'),
    (N'N-SE-HUB', N'N-SE-LOAD-02', 720.0000, '2025-01-01T00:00:00'),
    (N'TX-HUB', N'TX-WEST-01', 1400.0000, '2025-01-01T00:00:00'),
    (N'TX-HUB', N'TX-SOUTH-02', 1210.0000, '2025-01-01T00:00:00'),
    (N'PJM-HUB', N'PJM-EAST-11', 1115.0000, '2025-01-01T00:00:00'),
    (N'PJM-HUB', N'PJM-CENTRAL-07', 980.0000, '2025-01-01T00:00:00');

INSERT INTO @InboundTelemetry
(
    MarketCode,
    ControlAreaCode,
    RegionCode,
    ParentNodeCode,
    NodeCode,
    FeederCode,
    ResourceCode,
    ResourceTypeCode,
    DispatchModeCode,
    IntervalCode,
    TelemetryUtc,
    IntervalStartUtc,
    IntervalEndUtc,
    ScheduledMw,
    ActualMw,
    ReserveMw,
    ReserveRequirementMw,
    FrequencyHz,
    VoltageKv,
    CongestionIndex,
    CurtailmentMw,
    TelemetryJson,
    DiagnosticXml
)
VALUES
    (
        N'NORDPOOL',
        N'SE1',
        N'NORDICS',
        NULL,
        N'N-SE-HUB',
        N'FDR-SE-001',
        N'HYDRO-ALFA',
        N'HYDRO',
        N'AUTO',
        N'I00',
        '2025-12-13T16:00:00',
        '2025-12-13T16:00:00',
        '2025-12-13T16:15:00',
        640.0000,
        588.0000,
        44.0000,
        68.0000,
        49.8420,
        405.0000,
        4.2000,
        0.0000,
        N'{"priority":"critical","fuel":"water","dispatch":{"manualOverride":false,"rampBandMw":35},"quality":{"telemetryLagSeconds":4}}',
        '<diag><event code="LOW_FREQ" severity="CRITICAL" /><event code="RESERVE_GAP" severity="HIGH" /></diag>'
    ),
    (
        N'NORDPOOL',
        N'SE1',
        N'NORDICS',
        N'N-SE-HUB',
        N'N-SE-LOAD-01',
        N'FDR-SE-002',
        N'BAT-ALFA',
        N'STORAGE',
        N'AUTO',
        N'I00',
        '2025-12-13T16:00:00',
        '2025-12-13T16:00:00',
        '2025-12-13T16:15:00',
        120.0000,
        141.5000,
        9.0000,
        12.0000,
        49.8560,
        132.0000,
        5.9000,
        0.0000,
        N'{"priority":"high","fuel":"battery","dispatch":{"manualOverride":false,"rampBandMw":18},"quality":{"telemetryLagSeconds":2}}',
        '<diag><event code="CONGESTION_RISE" severity="HIGH" /></diag>'
    ),
    (
        N'ERCOT',
        N'WEST',
        N'AMERICAS',
        NULL,
        N'TX-HUB',
        N'FDR-TX-010',
        N'GAS-OMEGA',
        N'GAS',
        N'MANUAL',
        N'I01',
        '2025-12-13T16:15:00',
        '2025-12-13T16:15:00',
        '2025-12-13T16:30:00',
        880.0000,
        801.0000,
        55.0000,
        96.0000,
        59.9150,
        345.0000,
        8.6000,
        12.0000,
        N'{"priority":"critical","fuel":"gas","dispatch":{"manualOverride":true,"rampBandMw":42},"quality":{"telemetryLagSeconds":7}}',
        '<diag><event code="LOW_FREQ" severity="CRITICAL" /><event code="CURTAILMENT" severity="MEDIUM" /></diag>'
    ),
    (
        N'PJM',
        N'EAST',
        N'AMERICAS',
        NULL,
        N'PJM-HUB',
        N'FDR-PJ-021',
        N'SOLAR-EAST',
        N'SOLAR',
        N'AUTO',
        N'I01',
        '2025-12-13T16:15:00',
        '2025-12-13T16:15:00',
        '2025-12-13T16:30:00',
        510.0000,
        433.0000,
        18.0000,
        38.0000,
        59.9480,
        230.0000,
        7.5000,
        24.0000,
        N'{"priority":"high","fuel":"solar","dispatch":{"manualOverride":false,"rampBandMw":12},"quality":{"telemetryLagSeconds":5}}',
        '<diag><event code="CLOUD_FRONT" severity="HIGH" /></diag>'
    );

INSERT INTO #GridTelemetryStage
(
    MarketCode,
    ControlAreaCode,
    RegionCode,
    ParentNodeCode,
    NodeCode,
    FeederCode,
    ResourceCode,
    ResourceTypeCode,
    DispatchModeCode,
    IntervalCode,
    TelemetryUtc,
    IntervalStartUtc,
    IntervalEndUtc,
    ScheduledMw,
    ActualMw,
    ReserveMw,
    ReserveRequirementMw,
    FrequencyHz,
    VoltageKv,
    CongestionIndex,
    CurtailmentMw,
    TelemetryJson,
    DiagnosticXml
)
SELECT
    t.MarketCode,
    t.ControlAreaCode,
    t.RegionCode,
    t.ParentNodeCode,
    t.NodeCode,
    t.FeederCode,
    t.ResourceCode,
    t.ResourceTypeCode,
    t.DispatchModeCode,
    t.IntervalCode,
    t.TelemetryUtc,
    t.IntervalStartUtc,
    t.IntervalEndUtc,
    t.ScheduledMw,
    t.ActualMw,
    t.ReserveMw,
    t.ReserveRequirementMw,
    t.FrequencyHz,
    t.VoltageKv,
    t.CongestionIndex,
    t.CurtailmentMw,
    t.TelemetryJson,
    t.DiagnosticXml
FROM @InboundTelemetry AS t;

BEGIN TRY
    BEGIN TRANSACTION;
    SAVE TRANSACTION BeforeBalancingEvaluation;

    WITH NodeGraph AS
    (
        SELECT
            g.NodeCode,
            g.ParentNodeCode,
            0 AS TopologyLevel,
            CAST(CONCAT(g.NodeCode, N'>') AS NVARCHAR(4000)) AS TopologyPath
        FROM #GridTelemetryStage AS g
        WHERE g.ParentNodeCode IS NULL

        UNION ALL

        SELECT
            c.NodeCode,
            c.ParentNodeCode,
            ng.TopologyLevel + 1,
            CAST(ng.TopologyPath + c.NodeCode + N'>' AS NVARCHAR(4000))
        FROM #GridTelemetryStage AS c
        INNER JOIN NodeGraph AS ng
            ON c.ParentNodeCode = ng.NodeCode
    )
    INSERT INTO #FeederTopology
    (
        NodeCode,
        ParentNodeCode,
        TopologyLevel,
        TopologyPath
    )
    SELECT
        ng.NodeCode,
        ng.ParentNodeCode,
        ng.TopologyLevel,
        ng.TopologyPath
    FROM NodeGraph AS ng
    OPTION (MAXRECURSION 100);

    WITH TelemetryEnrichment AS
    (
        SELECT
            g.StageTelemetryId,
            g.MarketCode,
            g.ControlAreaCode,
            g.RegionCode,
            g.NodeCode,
            g.FeederCode,
            g.ResourceCode,
            g.ResourceTypeCode,
            g.DispatchModeCode,
            g.IntervalCode,
            g.TelemetryUtc,
            g.IntervalStartUtc,
            g.IntervalEndUtc,
            g.ScheduledMw,
            g.ActualMw,
            g.ReserveMw,
            g.ReserveRequirementMw,
            g.FrequencyHz,
            g.VoltageKv,
            g.CongestionIndex,
            g.CurtailmentMw,
            g.ImbalanceMw,
            mp.ReservePolicyCode,
            mp.CriticalFrequencyFloor,
            mp.MaxCongestionIndex,
            ISNULL(JSON_QUERY(g.TelemetryJson, '$.priority'), JSON_VALUE(g.TelemetryJson, '$.priority')) AS DispatchPriority,
            TRY_CAST(ISNULL(JSON_QUERY(g.TelemetryJson, '$.dispatch.manualOverride'), JSON_VALUE(g.TelemetryJson, '$.dispatch.manualOverride')) AS BIT) AS IsManualOverride,
            TRY_CAST(ISNULL(JSON_QUERY(g.TelemetryJson, '$.dispatch.rampBandMw'), JSON_VALUE(g.TelemetryJson, '$.dispatch.rampBandMw')) AS NUMERIC(19, 4)) AS RampBandMw,
            TRY_CAST(ISNULL(JSON_QUERY(g.TelemetryJson, '$.quality.telemetryLagSeconds'), JSON_VALUE(g.TelemetryJson, '$.quality.telemetryLagSeconds')) AS INTEGER) AS TelemetryLagSeconds,
            ft.TopologyLevel,
            ft.TopologyPath,
            DENSE_RANK() OVER (PARTITION BY g.MarketCode, g.ControlAreaCode ORDER BY ABS(g.ImbalanceMw) DESC, g.TelemetryUtc DESC) AS ImbalanceRank,
            SUM(g.ReserveMw) OVER (PARTITION BY g.MarketCode, g.ControlAreaCode, g.IntervalCode) AS TotalReserveByAreaInterval
        FROM #GridTelemetryStage AS g
        INNER JOIN @MarketProfile AS mp
            ON mp.MarketCode = g.MarketCode
        LEFT JOIN #FeederTopology AS ft
            ON ft.NodeCode = g.NodeCode
    ),
    FlowExpansion AS
    (
        SELECT
            te.NodeCode AS RootNodeCode,
            te.NodeCode AS CurrentNodeCode,
            CAST(0.0000 AS NUMERIC(19, 4)) AS TransferRequirementMw,
            0 AS FlowLevel,
            CAST(te.NodeCode + N'>' AS NVARCHAR(4000)) AS FlowPath
        FROM TelemetryEnrichment AS te

        UNION ALL

        SELECT
            fx.RootNodeCode,
            e.ChildNodeCode,
            CAST(fx.TransferRequirementMw + e.TransferLimitMw AS NUMERIC(19, 4)),
            fx.FlowLevel + 1,
            CAST(fx.FlowPath + e.ChildNodeCode + N'>' AS NVARCHAR(4000))
        FROM FlowExpansion AS fx
        INNER JOIN @TransmissionEdges AS e
            ON e.ParentNodeCode = fx.CurrentNodeCode
        WHERE fx.FlowLevel < 5
    ),
    BalancingSignals AS
    (
        SELECT
            te.StageTelemetryId,
            te.MarketCode,
            te.ControlAreaCode,
            te.NodeCode,
            te.ResourceCode,
            te.DispatchPriority,
            te.ReservePolicyCode,
            te.CriticalFrequencyFloor,
            te.MaxCongestionIndex,
            te.IsManualOverride,
            te.RampBandMw,
            te.TelemetryLagSeconds,
            te.ImbalanceMw,
            te.ReserveMw,
            te.ReserveRequirementMw,
            te.FrequencyHz,
            te.CongestionIndex,
            te.CurtailmentMw,
            te.ImbalanceRank,
            te.TotalReserveByAreaInterval,
            COUNT(*) AS ReachableEdgeCount,
            MAX(fx.FlowLevel) AS MaxFlowDepth,
            CASE
                WHEN te.ReserveMw < te.ReserveRequirementMw AND te.DispatchPriority = N'critical' THEN N'CRITICAL_RESERVE_SHORTFALL'
                WHEN te.FrequencyHz < te.CriticalFrequencyFloor THEN N'FREQUENCY_CONTAINMENT_BREACH'
                WHEN te.CongestionIndex > te.MaxCongestionIndex THEN N'TRANSMISSION_CONGESTION_BREACH'
                WHEN ABS(te.ImbalanceMw) > 50.0000 AND te.IsManualOverride = 1 THEN N'MANUAL_DISPATCH_IMBALANCE'
                ELSE N'NORMAL'
            END AS SignalCode
        FROM TelemetryEnrichment AS te
        LEFT JOIN FlowExpansion AS fx
            ON fx.RootNodeCode = te.NodeCode
        GROUP BY
            te.StageTelemetryId,
            te.MarketCode,
            te.ControlAreaCode,
            te.NodeCode,
            te.ResourceCode,
            te.DispatchPriority,
            te.ReservePolicyCode,
            te.CriticalFrequencyFloor,
            te.MaxCongestionIndex,
            te.IsManualOverride,
            te.RampBandMw,
            te.TelemetryLagSeconds,
            te.ImbalanceMw,
            te.ReserveMw,
            te.ReserveRequirementMw,
            te.FrequencyHz,
            te.CongestionIndex,
            te.CurtailmentMw,
            te.ImbalanceRank,
            te.TotalReserveByAreaInterval
    )
    INSERT INTO #ReserveAlertQueue
    (
        AlertCategory,
        SeverityCode,
        MarketCode,
        ControlAreaCode,
        NodeCode,
        ResourceCode,
        AlertMessage,
        AlertPayload
    )
    SELECT
        N'GRID_BALANCING_SIGNAL',
        CASE
            WHEN s.SignalCode IN (N'CRITICAL_RESERVE_SHORTFALL', N'FREQUENCY_CONTAINMENT_BREACH') THEN N'CRITICAL'
            WHEN s.SignalCode IN (N'TRANSMISSION_CONGESTION_BREACH', N'MANUAL_DISPATCH_IMBALANCE') THEN N'HIGH'
            ELSE N'MEDIUM'
        END,
        s.MarketCode,
        s.ControlAreaCode,
        s.NodeCode,
        s.ResourceCode,
        CONCAT(N'Balancing signal detected for node ', s.NodeCode, N': ', s.SignalCode),
        (
            SELECT
                s.DispatchPriority AS [priority],
                s.ReservePolicyCode AS [reservePolicy],
                s.ReserveMw AS [reserveMw],
                s.ReserveRequirementMw AS [reserveRequirementMw],
                s.FrequencyHz AS [frequencyHz],
                s.CongestionIndex AS [congestionIndex],
                s.ImbalanceMw AS [imbalanceMw],
                s.ReachableEdgeCount AS [reachableEdgeCount],
                s.MaxFlowDepth AS [maxFlowDepth]
            FOR JSON PATH, WITHOUT_ARRAY_WRAPPER, INCLUDE_NULL_VALUES
        )
    FROM BalancingSignals AS s
    WHERE s.SignalCode <> N'NORMAL';

    INSERT INTO #IntervalPivotSeed
    (
        MarketCode,
        ControlAreaCode,
        IntervalCode,
        FunctionalMw
    )
    SELECT
        g.MarketCode,
        g.ControlAreaCode,
        g.IntervalCode,
        g.ActualMw + g.ReserveMw - g.CurtailmentMw
    FROM #GridTelemetryStage AS g;

    DECLARE @PivotColumns NVARCHAR(MAX);
    DECLARE @PivotSql NVARCHAR(MAX);

    SELECT
        @PivotColumns = STRING_AGG(QUOTENAME(IntervalCode), N',')
    FROM
    (
        SELECT DISTINCT IntervalCode
        FROM #IntervalPivotSeed
    ) AS interval_codes;

    SET @PivotSql = N'
        SELECT MarketCode, ControlAreaCode, ' + @PivotColumns + N'
        INTO #IntervalBalanceMatrix
        FROM
        (
            SELECT MarketCode, ControlAreaCode, IntervalCode, FunctionalMw
            FROM #IntervalPivotSeed
        ) src
        PIVOT
        (
            SUM(FunctionalMw)
            FOR IntervalCode IN (' + @PivotColumns + N')
        ) p;';

    EXEC sys.sp_executesql @PivotSql;

    MERGE INTO dbo.GridBalancingSnapshot AS target
    USING
    (
        SELECT
            g.MarketCode,
            g.ControlAreaCode,
            COUNT(*) AS TelemetryPointCount,
            SUM(g.ActualMw) AS TotalActualMw,
            SUM(g.ReserveMw) AS TotalReserveMw,
            SUM(g.ReserveRequirementMw) AS TotalReserveRequirementMw,
            AVG(g.FrequencyHz) AS AvgFrequencyHz,
            MAX(g.TelemetryUtc) AS LastTelemetryUtc,
            SYSUTCDATETIME() AS SnapshotUtc
        FROM #GridTelemetryStage AS g
        GROUP BY
            g.MarketCode,
            g.ControlAreaCode
    ) AS source
        ON target.MarketCode = source.MarketCode
       AND target.ControlAreaCode = source.ControlAreaCode
    WHEN MATCHED THEN
        UPDATE SET
            target.TelemetryPointCount = source.TelemetryPointCount,
            target.TotalActualMw = source.TotalActualMw,
            target.TotalReserveMw = source.TotalReserveMw,
            target.TotalReserveRequirementMw = source.TotalReserveRequirementMw,
            target.AvgFrequencyHz = source.AvgFrequencyHz,
            target.LastTelemetryUtc = source.LastTelemetryUtc,
            target.LastRefreshUtc = source.SnapshotUtc
    WHEN NOT MATCHED THEN
        INSERT
        (
            MarketCode,
            ControlAreaCode,
            TelemetryPointCount,
            TotalActualMw,
            TotalReserveMw,
            TotalReserveRequirementMw,
            AvgFrequencyHz,
            LastTelemetryUtc,
            LastRefreshUtc
        )
        VALUES
        (
            source.MarketCode,
            source.ControlAreaCode,
            source.TelemetryPointCount,
            source.TotalActualMw,
            source.TotalReserveMw,
            source.TotalReserveRequirementMw,
            source.AvgFrequencyHz,
            source.LastTelemetryUtc,
            source.SnapshotUtc
        )
    OUTPUT
        $action,
        inserted.MarketCode,
        inserted.ControlAreaCode,
        inserted.LastRefreshUtc
    INTO dbo.GridBalancingAudit
    (
        MergeAction,
        MarketCode,
        ControlAreaCode,
        AuditUtc
    );

    IF EXISTS
    (
        SELECT 1
        FROM #ReserveAlertQueue
        WHERE SeverityCode = N'CRITICAL'
    )
    BEGIN
        WAITFOR DELAY '00:00:02';
    END;

    DECLARE @DispatchMarketCode AS NVARCHAR(20);
    DECLARE @DispatchControlAreaCode AS NVARCHAR(20);
    DECLARE @DispatchNodeCode AS NVARCHAR(30);

    DECLARE ReserveDispatchCursor CURSOR LOCAL FAST_FORWARD FOR
        SELECT
            q.MarketCode,
            q.ControlAreaCode,
            q.NodeCode
        FROM #ReserveAlertQueue AS q
        WHERE q.SeverityCode IN (N'CRITICAL', N'HIGH')
        ORDER BY q.AlertUtc, q.AlertId;

    OPEN ReserveDispatchCursor;
    FETCH NEXT FROM ReserveDispatchCursor
        INTO @DispatchMarketCode, @DispatchControlAreaCode, @DispatchNodeCode;

    WHILE @@FETCH_STATUS = 0
    BEGIN
        EXEC dbo.usp_DispatchGridReserveAlert
            @MarketCode = @DispatchMarketCode,
            @ControlAreaCode = @DispatchControlAreaCode,
            @NodeCode = @DispatchNodeCode,
            @RequestedUtc = SYSUTCDATETIME();

        FETCH NEXT FROM ReserveDispatchCursor
            INTO @DispatchMarketCode, @DispatchControlAreaCode, @DispatchNodeCode;
    END;

    CLOSE ReserveDispatchCursor;
    DEALLOCATE ReserveDispatchCursor;

    INSERT INTO dbo.GridBalancingRuns
    (
        RunUtc,
        RunCategory,
        FinalStateCode,
        AlertEnvelopeJson,
        TopologyEnvelopeXml
    )
    SELECT
        SYSUTCDATETIME(),
        N'GRID_BALANCING',
        CASE
            WHEN EXISTS (SELECT 1 FROM #ReserveAlertQueue WHERE SeverityCode = N'CRITICAL') THEN N'ESCALATED'
            WHEN EXISTS (SELECT 1 FROM #ReserveAlertQueue) THEN N'WARNINGS'
            ELSE N'CLEAR'
        END,
        (
            SELECT
                q.AlertCategory,
                q.SeverityCode,
                q.MarketCode,
                q.ControlAreaCode,
                q.NodeCode,
                q.ResourceCode,
                q.AlertMessage
            FROM #ReserveAlertQueue AS q
            FOR JSON PATH, INCLUDE_NULL_VALUES
        ),
        (
            SELECT
                t.NodeCode AS [@nodeCode],
                t.ParentNodeCode AS [@parentNodeCode],
                t.TopologyLevel AS [@level],
                t.TopologyPath AS [path]
            FROM #FeederTopology AS t
            FOR XML PATH('node'), ROOT('topology'), TYPE
        );

    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    IF CURSOR_STATUS('local', 'ReserveDispatchCursor') >= -1
    BEGIN
        CLOSE ReserveDispatchCursor;
        DEALLOCATE ReserveDispatchCursor;
    END;

    IF XACT_STATE() = -1
        ROLLBACK TRANSACTION;
    ELSE IF XACT_STATE() = 1
        ROLLBACK TRANSACTION BeforeBalancingEvaluation;

    INSERT INTO #ReserveAlertQueue
    (
        AlertCategory,
        SeverityCode,
        MarketCode,
        ControlAreaCode,
        NodeCode,
        ResourceCode,
        AlertMessage,
        AlertPayload
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
        CONCAT
        (
            N'{"errorNumber":', ERROR_NUMBER(),
            N',"errorLine":', ERROR_LINE(),
            N',"errorState":', ERROR_STATE(),
            N',"procedure":"', COALESCE(ERROR_PROCEDURE(), N''), N'"}'
        )
    );

    THROW;
END CATCH;

SELECT
    q.AlertId,
    q.AlertUtc,
    q.AlertCategory,
    q.SeverityCode,
    q.MarketCode,
    q.ControlAreaCode,
    q.NodeCode,
    q.ResourceCode,
    q.AlertMessage,
    q.AlertPayload
FROM #ReserveAlertQueue AS q
ORDER BY
    CASE q.SeverityCode
        WHEN N'CRITICAL' THEN 1
        WHEN N'HIGH' THEN 2
        WHEN N'MEDIUM' THEN 3
        ELSE 4
    END,
    q.AlertUtc DESC,
    q.AlertId DESC;

SELECT
    t.TopologyRowId,
    t.NodeCode,
    t.ParentNodeCode,
    t.TopologyLevel,
    t.TopologyPath
FROM #FeederTopology AS t
ORDER BY
    t.NodeCode,
    t.TopologyLevel;

DROP TABLE IF EXISTS #IntervalBalanceMatrix;
DROP TABLE IF EXISTS #IntervalPivotSeed;
DROP TABLE IF EXISTS #FeederTopology;
DROP TABLE IF EXISTS #ReserveAlertQueue;
DROP TABLE IF EXISTS #GridTelemetryStage;
GO

EXEC dbo.usp_FinalizeGridBalancingWindow
    @WindowCode = N'GLOBAL_GRID_BALANCING',
    @ClosedUtc = SYSUTCDATETIME(),
    @ClosedBy = ORIGINAL_LOGIN();
