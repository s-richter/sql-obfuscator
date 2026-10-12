/* Extreme T-SQL stress sample 9 */
/* Purpose: clearing liquidity orchestration workflow with recursive obligation chains, */
/* shortfall alerts, bucket pivots, JSON/XML envelopes, savepoints, cursor dispatch, */
/* and procedural exception recovery. */

SET NOCOUNT ON;
SET XACT_ABORT ON;
SET DEADLOCK_PRIORITY HIGH;

DROP TABLE IF EXISTS #SettlementObligationStage;
DROP TABLE IF EXISTS #ClearingAlertQueue;
DROP TABLE IF EXISTS #ObligationHierarchy;
DROP TABLE IF EXISTS #CyclePivotSeed;

CREATE TABLE #SettlementObligationStage
(
    StageObligationId BIGINT IDENTITY(1, 1) PRIMARY KEY,
    LoadBatchId UNIQUEIDENTIFIER NOT NULL DEFAULT NEWID(),
    ClearingRunCode NVARCHAR(30) NOT NULL,
    ClearingMemberCode NVARCHAR(30) NOT NULL,
    ParentObligationCode NVARCHAR(40) NULL,
    ObligationCode NVARCHAR(40) NOT NULL,
    SettlementAccountCode NVARCHAR(40) NOT NULL,
    CurrencyCode CHAR(3) NOT NULL,
    CycleBucketCode NVARCHAR(20) NOT NULL,
    CollateralTierCode NVARCHAR(20) NOT NULL,
    PaymentRailCode NVARCHAR(20) NOT NULL,
    SnapshotUtc DATETIME2(3) NOT NULL,
    ValueDate DATE NOT NULL,
    GrossPayable NUMERIC(19, 4) NOT NULL,
    GrossReceivable NUMERIC(19, 4) NOT NULL,
    AvailableLiquidity NUMERIC(19, 4) NOT NULL,
    RequiredLiquidity NUMERIC(19, 4) NOT NULL,
    ReserveBuffer NUMERIC(19, 4) NOT NULL,
    StressLoss NUMERIC(19, 4) NOT NULL,
    QueueDepthScore INTEGER NULL,
    RegulatoryThreshold NUMERIC(19, 4) NOT NULL,
    LiquidityCoverage AS (
        CASE
            WHEN RequiredLiquidity = 0 THEN 0
            ELSE (AvailableLiquidity + ReserveBuffer - StressLoss) / NULLIF(RequiredLiquidity, 0)
        END
    ) PERSISTED,
    ObligationJson NVARCHAR(MAX) NULL,
    DiagnosticXml XML NULL,
    CreatedUtc DATETIME2(3) NOT NULL DEFAULT SYSUTCDATETIME()
);

CREATE TABLE #ClearingAlertQueue
(
    AlertId BIGINT IDENTITY(1, 1) PRIMARY KEY,
    AlertUtc DATETIME2(3) NOT NULL DEFAULT SYSUTCDATETIME(),
    AlertCategory NVARCHAR(40) NOT NULL,
    SeverityCode NVARCHAR(20) NOT NULL,
    ClearingRunCode NVARCHAR(30) NULL,
    ClearingMemberCode NVARCHAR(30) NULL,
    ObligationCode NVARCHAR(40) NULL,
    SettlementAccountCode NVARCHAR(40) NULL,
    AlertMessage NVARCHAR(4000) NOT NULL,
    AlertPayload NVARCHAR(MAX) NULL
);

CREATE TABLE #ObligationHierarchy
(
    HierarchyRowId BIGINT IDENTITY(1, 1) PRIMARY KEY,
    ObligationCode NVARCHAR(40) NOT NULL,
    ParentObligationCode NVARCHAR(40) NULL,
    HierarchyLevel INTEGER NOT NULL,
    HierarchyPath NVARCHAR(4000) NOT NULL
);

CREATE TABLE #CyclePivotSeed
(
    ClearingRunCode NVARCHAR(30) NOT NULL,
    ClearingMemberCode NVARCHAR(30) NOT NULL,
    CycleBucketCode NVARCHAR(20) NOT NULL,
    FunctionalLiquidity NUMERIC(19, 4) NOT NULL
);

DECLARE @RunProfile TABLE
(
    ClearingRunCode NVARCHAR(30) PRIMARY KEY,
    TargetCoverage NUMERIC(19, 4) NOT NULL,
    EscalationBandCode NVARCHAR(20) NOT NULL,
    MaxQueueDepthScore INTEGER NOT NULL,
    RunProfileJson NVARCHAR(MAX) NULL
);

DECLARE @ObligationEdges TABLE
(
    ParentObligationCode NVARCHAR(40) NOT NULL,
    ChildObligationCode NVARCHAR(40) NOT NULL,
    TransferCapacity NUMERIC(19, 4) NOT NULL,
    EffectiveUtc DATETIME2(3) NOT NULL,
    PRIMARY KEY (ParentObligationCode, ChildObligationCode, EffectiveUtc)
);

DECLARE @InboundObligations TABLE
(
    FeedRowId INTEGER IDENTITY(1, 1) PRIMARY KEY,
    ClearingRunCode NVARCHAR(30) NOT NULL,
    ClearingMemberCode NVARCHAR(30) NOT NULL,
    ParentObligationCode NVARCHAR(40) NULL,
    ObligationCode NVARCHAR(40) NOT NULL,
    SettlementAccountCode NVARCHAR(40) NOT NULL,
    CurrencyCode CHAR(3) NOT NULL,
    CycleBucketCode NVARCHAR(20) NOT NULL,
    CollateralTierCode NVARCHAR(20) NOT NULL,
    PaymentRailCode NVARCHAR(20) NOT NULL,
    SnapshotUtc DATETIME2(3) NOT NULL,
    ValueDate DATE NOT NULL,
    GrossPayable NUMERIC(19, 4) NOT NULL,
    GrossReceivable NUMERIC(19, 4) NOT NULL,
    AvailableLiquidity NUMERIC(19, 4) NOT NULL,
    RequiredLiquidity NUMERIC(19, 4) NOT NULL,
    ReserveBuffer NUMERIC(19, 4) NOT NULL,
    StressLoss NUMERIC(19, 4) NOT NULL,
    QueueDepthScore INTEGER NULL,
    RegulatoryThreshold NUMERIC(19, 4) NOT NULL,
    ObligationJson NVARCHAR(MAX) NULL,
    DiagnosticXml XML NULL
);

INSERT INTO @RunProfile
(
    ClearingRunCode,
    TargetCoverage,
    EscalationBandCode,
    MaxQueueDepthScore,
    RunProfileJson
)
VALUES
    (N'CLR-EU-AM', 1.0800, N'BAND1', 70, N'{"window":"morning","operator":"euroclear","priority":"cash"}'),
    (N'CLR-US-PM', 1.0500, N'BAND2', 64, N'{"window":"afternoon","operator":"dtcc","priority":"usd"}'),
    (N'CLR-APAC-NET', 1.0200, N'BAND3', 58, N'{"window":"night","operator":"jpx","priority":"yen"}');

INSERT INTO @ObligationEdges
(
    ParentObligationCode,
    ChildObligationCode,
    TransferCapacity,
    EffectiveUtc
)
VALUES
    (N'OBL-ROOT-100', N'OBL-CHILD-101', 125.0000, '2025-01-01T00:00:00'),
    (N'OBL-ROOT-100', N'OBL-CHILD-102', 85.0000, '2025-01-01T00:00:00'),
    (N'OBL-ROOT-500', N'OBL-CHILD-501', 110.0000, '2025-01-01T00:00:00'),
    (N'OBL-ROOT-500', N'OBL-CHILD-502', 72.0000, '2025-01-01T00:00:00');

INSERT INTO @InboundObligations
(
    ClearingRunCode,
    ClearingMemberCode,
    ParentObligationCode,
    ObligationCode,
    SettlementAccountCode,
    CurrencyCode,
    CycleBucketCode,
    CollateralTierCode,
    PaymentRailCode,
    SnapshotUtc,
    ValueDate,
    GrossPayable,
    GrossReceivable,
    AvailableLiquidity,
    RequiredLiquidity,
    ReserveBuffer,
    StressLoss,
    QueueDepthScore,
    RegulatoryThreshold,
    ObligationJson,
    DiagnosticXml
)
VALUES
    (
        N'CLR-EU-AM',
        N'MBR-EU-01',
        NULL,
        N'OBL-ROOT-100',
        N'SA-EUR-001',
        N'EUR',
        N'CYCLE-1',
        N'TIER1',
        N'TARGET2',
        '2025-12-19T06:30:00',
        '2025-12-19',
        980.0000,
        210.0000,
        640.0000,
        760.0000,
        65.0000,
        48.0000,
        76,
        1.0800,
        N'{"priority":"critical","liquidity":{"manualTopup":false,"buffer":16},"ops":{"queueHold":true}}',
        '<diag><event code="LIQUIDITY_GAP" severity="CRITICAL" /><event code="QUEUE_PRESSURE" severity="HIGH" /></diag>'
    ),
    (
        N'CLR-EU-AM',
        N'MBR-EU-01',
        N'OBL-ROOT-100',
        N'OBL-CHILD-101',
        N'SA-EUR-002',
        N'EUR',
        N'CYCLE-2',
        N'TIER1',
        N'TARGET2',
        '2025-12-19T06:30:00',
        '2025-12-19',
        240.0000,
        120.0000,
        150.0000,
        190.0000,
        18.0000,
        9.0000,
        59,
        1.0600,
        N'{"priority":"high","liquidity":{"manualTopup":false,"buffer":7},"ops":{"queueHold":false}}',
        '<diag><event code="QUEUE_BUILD" severity="MEDIUM" /></diag>'
    ),
    (
        N'CLR-US-PM',
        N'MBR-US-77',
        NULL,
        N'OBL-ROOT-500',
        N'SA-USD-777',
        N'USD',
        N'CYCLE-1',
        N'TIER2',
        N'FEDWIRE',
        '2025-12-19T19:10:00',
        '2025-12-19',
        760.0000,
        140.0000,
        430.0000,
        610.0000,
        44.0000,
        38.0000,
        67,
        1.0500,
        N'{"priority":"critical","liquidity":{"manualTopup":true,"buffer":11},"ops":{"queueHold":true}}',
        '<diag><event code="TOPUP_DELAY" severity="CRITICAL" /><event code="RAIL_BACKLOG" severity="HIGH" /></diag>'
    ),
    (
        N'CLR-APAC-NET',
        N'MBR-JP-11',
        NULL,
        N'OBL-ROOT-901',
        N'SA-JPY-111',
        N'JPY',
        N'CYCLE-3',
        N'TIER3',
        N'BOJNET',
        '2025-12-19T01:40:00',
        '2025-12-19',
        310.0000,
        220.0000,
        205.0000,
        188.0000,
        12.0000,
        6.0000,
        42,
        1.0200,
        N'{"priority":"medium","liquidity":{"manualTopup":false,"buffer":3},"ops":{"queueHold":false}}',
        '<diag><event code="NORMAL" severity="INFO" /></diag>'
    );

INSERT INTO #SettlementObligationStage
(
    ClearingRunCode,
    ClearingMemberCode,
    ParentObligationCode,
    ObligationCode,
    SettlementAccountCode,
    CurrencyCode,
    CycleBucketCode,
    CollateralTierCode,
    PaymentRailCode,
    SnapshotUtc,
    ValueDate,
    GrossPayable,
    GrossReceivable,
    AvailableLiquidity,
    RequiredLiquidity,
    ReserveBuffer,
    StressLoss,
    QueueDepthScore,
    RegulatoryThreshold,
    ObligationJson,
    DiagnosticXml
)
SELECT
    i.ClearingRunCode,
    i.ClearingMemberCode,
    i.ParentObligationCode,
    i.ObligationCode,
    i.SettlementAccountCode,
    i.CurrencyCode,
    i.CycleBucketCode,
    i.CollateralTierCode,
    i.PaymentRailCode,
    i.SnapshotUtc,
    i.ValueDate,
    i.GrossPayable,
    i.GrossReceivable,
    i.AvailableLiquidity,
    i.RequiredLiquidity,
    i.ReserveBuffer,
    i.StressLoss,
    i.QueueDepthScore,
    i.RegulatoryThreshold,
    i.ObligationJson,
    i.DiagnosticXml
FROM @InboundObligations AS i;

BEGIN TRY
    BEGIN TRANSACTION;
    SAVE TRANSACTION BeforeClearingEvaluation;

    WITH ObligationTree AS
    (
        SELECT
            o.ObligationCode,
            o.ParentObligationCode,
            0 AS HierarchyLevel,
            CAST(CONCAT(o.ObligationCode, N'>') AS NVARCHAR(4000)) AS HierarchyPath
        FROM #SettlementObligationStage AS o
        WHERE o.ParentObligationCode IS NULL

        UNION ALL

        SELECT
            c.ObligationCode,
            c.ParentObligationCode,
            ot.HierarchyLevel + 1,
            CAST(ot.HierarchyPath + c.ObligationCode + N'>' AS NVARCHAR(4000))
        FROM #SettlementObligationStage AS c
        INNER JOIN ObligationTree AS ot
            ON c.ParentObligationCode = ot.ObligationCode
    )
    INSERT INTO #ObligationHierarchy
    (
        ObligationCode,
        ParentObligationCode,
        HierarchyLevel,
        HierarchyPath
    )
    SELECT
        ot.ObligationCode,
        ot.ParentObligationCode,
        ot.HierarchyLevel,
        ot.HierarchyPath
    FROM ObligationTree AS ot
    OPTION (MAXRECURSION 100);

    WITH ObligationEnrichment AS
    (
        SELECT
            o.StageObligationId,
            o.ClearingRunCode,
            o.ClearingMemberCode,
            o.ObligationCode,
            o.SettlementAccountCode,
            o.CurrencyCode,
            o.CycleBucketCode,
            o.CollateralTierCode,
            o.PaymentRailCode,
            o.SnapshotUtc,
            o.GrossPayable,
            o.GrossReceivable,
            o.AvailableLiquidity,
            o.RequiredLiquidity,
            o.ReserveBuffer,
            o.StressLoss,
            o.QueueDepthScore,
            o.RegulatoryThreshold,
            o.LiquidityCoverage,
            rp.TargetCoverage,
            rp.EscalationBandCode,
            rp.MaxQueueDepthScore,
            ISNULL(JSON_QUERY(o.ObligationJson, '$.priority'), JSON_VALUE(o.ObligationJson, '$.priority')) AS PriorityCode,
            TRY_CAST(ISNULL(JSON_QUERY(o.ObligationJson, '$.liquidity.manualTopup'), JSON_VALUE(o.ObligationJson, '$.liquidity.manualTopup')) AS BIT) AS IsManualTopup,
            TRY_CAST(ISNULL(JSON_QUERY(o.ObligationJson, '$.liquidity.buffer'), JSON_VALUE(o.ObligationJson, '$.liquidity.buffer')) AS NUMERIC(19, 4)) AS ManualBuffer,
            TRY_CAST(ISNULL(JSON_QUERY(o.ObligationJson, '$.ops.queueHold'), JSON_VALUE(o.ObligationJson, '$.ops.queueHold')) AS BIT) AS IsQueueHeld,
            oh.HierarchyLevel,
            oh.HierarchyPath,
            DENSE_RANK() OVER (PARTITION BY o.ClearingRunCode, o.ClearingMemberCode ORDER BY o.LiquidityCoverage ASC, o.SnapshotUtc DESC) AS CoverageStressRank,
            SUM(o.RequiredLiquidity) OVER (PARTITION BY o.ClearingRunCode, o.ClearingMemberCode, o.CycleBucketCode) AS TotalRequiredByBucket
        FROM #SettlementObligationStage AS o
        INNER JOIN @RunProfile AS rp
            ON rp.ClearingRunCode = o.ClearingRunCode
        LEFT JOIN #ObligationHierarchy AS oh
            ON oh.ObligationCode = o.ObligationCode
    ),
    ObligationExpansion AS
    (
        SELECT
            oe.ObligationCode AS RootObligationCode,
            oe.ObligationCode AS CurrentObligationCode,
            CAST(0.0000 AS NUMERIC(19, 4)) AS TransferCapacityUsed,
            0 AS ObligationLevel,
            CAST(oe.ObligationCode + N'>' AS NVARCHAR(4000)) AS ObligationPath
        FROM ObligationEnrichment AS oe

        UNION ALL

        SELECT
            ox.RootObligationCode,
            e.ChildObligationCode,
            CAST(ox.TransferCapacityUsed + e.TransferCapacity AS NUMERIC(19, 4)),
            ox.ObligationLevel + 1,
            CAST(ox.ObligationPath + e.ChildObligationCode + N'>' AS NVARCHAR(4000))
        FROM ObligationExpansion AS ox
        INNER JOIN @ObligationEdges AS e
            ON e.ParentObligationCode = ox.CurrentObligationCode
        WHERE ox.ObligationLevel < 5
    ),
    ClearingSignals AS
    (
        SELECT
            oe.StageObligationId,
            oe.ClearingRunCode,
            oe.ClearingMemberCode,
            oe.ObligationCode,
            oe.SettlementAccountCode,
            oe.PriorityCode,
            oe.EscalationBandCode,
            oe.TargetCoverage,
            oe.MaxQueueDepthScore,
            oe.IsManualTopup,
            oe.ManualBuffer,
            oe.IsQueueHeld,
            oe.LiquidityCoverage,
            oe.RegulatoryThreshold,
            oe.QueueDepthScore,
            oe.TotalRequiredByBucket,
            oe.CoverageStressRank,
            COUNT(*) AS ReachableObligations,
            MAX(ox.ObligationLevel) AS MaxObligationDepth,
            CASE
                WHEN oe.LiquidityCoverage < oe.RegulatoryThreshold AND oe.PriorityCode = N'critical' THEN N'CRITICAL_LIQUIDITY_BREACH'
                WHEN oe.LiquidityCoverage < oe.TargetCoverage AND oe.IsManualTopup = 1 THEN N'MANUAL_TOPUP_GAP'
                WHEN oe.QueueDepthScore > oe.MaxQueueDepthScore THEN N'QUEUE_DEPTH_BREACH'
                WHEN oe.TotalRequiredByBucket > 900.0000 AND oe.IsQueueHeld = 1 THEN N'BUCKET_QUEUE_CONCENTRATION'
                ELSE N'NORMAL'
            END AS SignalCode
        FROM ObligationEnrichment AS oe
        LEFT JOIN ObligationExpansion AS ox
            ON ox.RootObligationCode = oe.ObligationCode
        GROUP BY
            oe.StageObligationId,
            oe.ClearingRunCode,
            oe.ClearingMemberCode,
            oe.ObligationCode,
            oe.SettlementAccountCode,
            oe.PriorityCode,
            oe.EscalationBandCode,
            oe.TargetCoverage,
            oe.MaxQueueDepthScore,
            oe.IsManualTopup,
            oe.ManualBuffer,
            oe.IsQueueHeld,
            oe.LiquidityCoverage,
            oe.RegulatoryThreshold,
            oe.QueueDepthScore,
            oe.TotalRequiredByBucket,
            oe.CoverageStressRank
    )
    INSERT INTO #ClearingAlertQueue
    (
        AlertCategory,
        SeverityCode,
        ClearingRunCode,
        ClearingMemberCode,
        ObligationCode,
        SettlementAccountCode,
        AlertMessage,
        AlertPayload
    )
    SELECT
        N'CLEARING_SIGNAL',
        CASE
            WHEN s.SignalCode IN (N'CRITICAL_LIQUIDITY_BREACH', N'MANUAL_TOPUP_GAP') THEN N'CRITICAL'
            WHEN s.SignalCode IN (N'QUEUE_DEPTH_BREACH', N'BUCKET_QUEUE_CONCENTRATION') THEN N'HIGH'
            ELSE N'MEDIUM'
        END,
        s.ClearingRunCode,
        s.ClearingMemberCode,
        s.ObligationCode,
        s.SettlementAccountCode,
        CONCAT(N'Clearing signal detected for obligation ', s.ObligationCode, N': ', s.SignalCode),
        (
            SELECT
                s.PriorityCode AS [priority],
                s.EscalationBandCode AS [escalationBand],
                s.LiquidityCoverage AS [liquidityCoverage],
                s.RegulatoryThreshold AS [regulatoryThreshold],
                s.QueueDepthScore AS [queueDepthScore],
                s.TotalRequiredByBucket AS [totalRequiredByBucket],
                s.ReachableObligations AS [reachableObligations],
                s.MaxObligationDepth AS [maxObligationDepth]
            FOR JSON PATH, ROOT('clearingAlert'), INCLUDE_NULL_VALUES
        )
    FROM ClearingSignals AS s
    WHERE s.SignalCode <> N'NORMAL';

    INSERT INTO #CyclePivotSeed
    (
        ClearingRunCode,
        ClearingMemberCode,
        CycleBucketCode,
        FunctionalLiquidity
    )
    SELECT
        o.ClearingRunCode,
        o.ClearingMemberCode,
        o.CycleBucketCode,
        o.AvailableLiquidity + o.GrossReceivable - o.GrossPayable
    FROM #SettlementObligationStage AS o;

    DECLARE @PivotColumns NVARCHAR(MAX);
    DECLARE @PivotSql NVARCHAR(MAX);

    SELECT
        @PivotColumns = STRING_AGG(QUOTENAME(CycleBucketCode), N',')
    FROM
    (
        SELECT DISTINCT CycleBucketCode
        FROM #CyclePivotSeed
    ) AS cycle_buckets;

    SET @PivotSql = N'
        SELECT ClearingRunCode, ClearingMemberCode, ' + @PivotColumns + N'
        INTO #CycleLiquidityMatrix
        FROM
        (
            SELECT ClearingRunCode, ClearingMemberCode, CycleBucketCode, FunctionalLiquidity
            FROM #CyclePivotSeed
        ) src
        PIVOT
        (
            SUM(FunctionalLiquidity)
            FOR CycleBucketCode IN (' + @PivotColumns + N')
        ) p;';

    EXEC sys.sp_executesql @PivotSql;

    MERGE INTO dbo.ClearingLiquiditySnapshot AS target
    USING
    (
        SELECT
            o.ClearingRunCode,
            o.ClearingMemberCode,
            COUNT(*) AS ObligationCount,
            SUM(o.GrossPayable) AS TotalGrossPayable,
            SUM(o.AvailableLiquidity) AS TotalAvailableLiquidity,
            AVG(o.LiquidityCoverage) AS AvgLiquidityCoverage,
            MAX(o.SnapshotUtc) AS LastSnapshotUtc,
            SYSUTCDATETIME() AS RefreshUtc
        FROM #SettlementObligationStage AS o
        GROUP BY
            o.ClearingRunCode,
            o.ClearingMemberCode
    ) AS source
        ON target.ClearingRunCode = source.ClearingRunCode
       AND target.ClearingMemberCode = source.ClearingMemberCode
    WHEN MATCHED THEN
        UPDATE SET
            target.ObligationCount = source.ObligationCount,
            target.TotalGrossPayable = source.TotalGrossPayable,
            target.TotalAvailableLiquidity = source.TotalAvailableLiquidity,
            target.AvgLiquidityCoverage = source.AvgLiquidityCoverage,
            target.LastSnapshotUtc = source.LastSnapshotUtc,
            target.LastRefreshUtc = source.RefreshUtc
    WHEN NOT MATCHED THEN
        INSERT
        (
            ClearingRunCode,
            ClearingMemberCode,
            ObligationCount,
            TotalGrossPayable,
            TotalAvailableLiquidity,
            AvgLiquidityCoverage,
            LastSnapshotUtc,
            LastRefreshUtc
        )
        VALUES
        (
            source.ClearingRunCode,
            source.ClearingMemberCode,
            source.ObligationCount,
            source.TotalGrossPayable,
            source.TotalAvailableLiquidity,
            source.AvgLiquidityCoverage,
            source.LastSnapshotUtc,
            source.RefreshUtc
        )
    OUTPUT
        $action,
        inserted.ClearingRunCode,
        inserted.ClearingMemberCode,
        inserted.LastRefreshUtc
    INTO dbo.ClearingLiquidityAudit
    (
        MergeAction,
        ClearingRunCode,
        ClearingMemberCode,
        AuditUtc
    );

    IF EXISTS
    (
        SELECT 1
        FROM #ClearingAlertQueue
        WHERE SeverityCode = N'CRITICAL'
    )
    BEGIN
        WAITFOR DELAY '00:00:01';
    END;

    DECLARE @DispatchRunCode AS NVARCHAR(30);
    DECLARE @DispatchMemberCode AS NVARCHAR(30);
    DECLARE @DispatchObligationCode AS NVARCHAR(40);

    DECLARE ClearingDispatchCursor CURSOR LOCAL FAST_FORWARD FOR
        SELECT
            q.ClearingRunCode,
            q.ClearingMemberCode,
            q.ObligationCode
        FROM #ClearingAlertQueue AS q
        WHERE q.SeverityCode IN (N'CRITICAL', N'HIGH')
        ORDER BY q.AlertUtc, q.AlertId;

    OPEN ClearingDispatchCursor;
    FETCH NEXT FROM ClearingDispatchCursor
        INTO @DispatchRunCode, @DispatchMemberCode, @DispatchObligationCode;

    WHILE @@FETCH_STATUS = 0
    BEGIN
        EXEC dbo.usp_DispatchClearingEscalation
            @ClearingRunCode = @DispatchRunCode,
            @ClearingMemberCode = @DispatchMemberCode,
            @ObligationCode = @DispatchObligationCode,
            @RequestedUtc = SYSUTCDATETIME();

        FETCH NEXT FROM ClearingDispatchCursor
            INTO @DispatchRunCode, @DispatchMemberCode, @DispatchObligationCode;
    END;

    CLOSE ClearingDispatchCursor;
    DEALLOCATE ClearingDispatchCursor;

    INSERT INTO dbo.ClearingLiquidityRuns
    (
        RunUtc,
        RunCategory,
        FinalStateCode,
        AlertEnvelopeJson,
        ObligationEnvelopeXml
    )
    SELECT
        SYSUTCDATETIME(),
        N'CLEARING_LIQUIDITY',
        CASE
            WHEN EXISTS (SELECT 1 FROM #ClearingAlertQueue WHERE SeverityCode = N'CRITICAL') THEN N'ESCALATED'
            WHEN EXISTS (SELECT 1 FROM #ClearingAlertQueue) THEN N'WARNINGS'
            ELSE N'CLEAR'
        END,
        (
            SELECT
                q.AlertCategory,
                q.SeverityCode,
                q.ClearingRunCode,
                q.ClearingMemberCode,
                q.ObligationCode,
                q.SettlementAccountCode,
                q.AlertMessage
            FROM #ClearingAlertQueue AS q
            FOR JSON PATH, ROOT('alerts'), INCLUDE_NULL_VALUES
        ),
        (
            SELECT
                h.ObligationCode AS [@obligationCode],
                h.ParentObligationCode AS [@parentObligationCode],
                h.HierarchyLevel AS [@level],
                h.HierarchyPath AS [path]
            FROM #ObligationHierarchy AS h
            FOR XML PATH('obligation'), ROOT('obligations'), TYPE
        );

    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    IF CURSOR_STATUS('local', 'ClearingDispatchCursor') >= -1
    BEGIN
        CLOSE ClearingDispatchCursor;
        DEALLOCATE ClearingDispatchCursor;
    END;

    IF XACT_STATE() = -1
        ROLLBACK TRANSACTION;
    ELSE IF XACT_STATE() = 1
        ROLLBACK TRANSACTION BeforeClearingEvaluation;

    INSERT INTO #ClearingAlertQueue
    (
        AlertCategory,
        SeverityCode,
        ClearingRunCode,
        ClearingMemberCode,
        ObligationCode,
        SettlementAccountCode,
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
    q.ClearingRunCode,
    q.ClearingMemberCode,
    q.ObligationCode,
    q.SettlementAccountCode,
    q.AlertMessage,
    q.AlertPayload
FROM #ClearingAlertQueue AS q
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
    h.HierarchyRowId,
    h.ObligationCode,
    h.ParentObligationCode,
    h.HierarchyLevel,
    h.HierarchyPath
FROM #ObligationHierarchy AS h
ORDER BY
    h.ObligationCode,
    h.HierarchyLevel;

DROP TABLE IF EXISTS #CycleLiquidityMatrix;
DROP TABLE IF EXISTS #CyclePivotSeed;
DROP TABLE IF EXISTS #ObligationHierarchy;
DROP TABLE IF EXISTS #ClearingAlertQueue;
DROP TABLE IF EXISTS #SettlementObligationStage;
GO

EXEC dbo.usp_FinalizeClearingLiquidityWindow
    @WindowCode = N'GLOBAL_CLEARING_LIQUIDITY',
    @ClosedUtc = SYSUTCDATETIME(),
    @ClosedBy = ORIGINAL_LOGIN();
