/* Extreme T-SQL stress sample 7 */
/* Purpose: collateral mobility command workflow with recursive pledge chains, */
/* settlement bucket pivots, margin breach escalation, JSON/XML envelopes, */
/* savepoints, dispatch queues, WAITFOR TIME, and procedural recovery logic. */

SET NOCOUNT ON;
SET XACT_ABORT ON;
SET DEADLOCK_PRIORITY HIGH;

DROP TABLE IF EXISTS #CollateralPositionStage;
DROP TABLE IF EXISTS #MarginAlertQueue;
DROP TABLE IF EXISTS #PledgeHierarchy;
DROP TABLE IF EXISTS #SettlementPivotSeed;

CREATE TABLE #CollateralPositionStage
(
    StageCollateralId BIGINT IDENTITY(1, 1) PRIMARY KEY,
    LoadBatchId UNIQUEIDENTIFIER NOT NULL DEFAULT NEWID(),
    LegalEntityCode NVARCHAR(30) NOT NULL,
    NettingSetCode NVARCHAR(30) NOT NULL,
    ParentPledgeCode NVARCHAR(40) NULL,
    PledgeCode NVARCHAR(40) NOT NULL,
    AssetId NVARCHAR(40) NOT NULL,
    AssetTypeCode NVARCHAR(20) NOT NULL,
    CurrencyCode CHAR(3) NOT NULL,
    SettlementBucketCode NVARCHAR(20) NOT NULL,
    EligibilityTierCode NVARCHAR(20) NOT NULL,
    CounterpartyCode NVARCHAR(30) NOT NULL,
    SnapshotUtc DATETIME2(3) NOT NULL,
    SettlementDate DATE NOT NULL,
    NominalValue NUMERIC(19, 4) NOT NULL,
    MarketValue NUMERIC(19, 4) NOT NULL,
    PledgedValue NUMERIC(19, 4) NOT NULL,
    RequiredMargin NUMERIC(19, 4) NOT NULL,
    IndependentAmount NUMERIC(19, 4) NOT NULL,
    HaircutPct NUMERIC(9, 4) NOT NULL,
    ConcentrationScore INTEGER NULL,
    RegulatoryFloor NUMERIC(19, 4) NOT NULL,
    MobilityRatio AS (
        CASE
            WHEN RequiredMargin = 0 THEN 0
            ELSE ((MarketValue - PledgedValue) * (1 - (HaircutPct / 100.0))) / NULLIF(RequiredMargin, 0)
        END
    ) PERSISTED,
    PositionJson NVARCHAR(MAX) NULL,
    DiagnosticXml XML NULL,
    CreatedUtc DATETIME2(3) NOT NULL DEFAULT SYSUTCDATETIME()
);

CREATE TABLE #MarginAlertQueue
(
    AlertId BIGINT IDENTITY(1, 1) PRIMARY KEY,
    AlertUtc DATETIME2(3) NOT NULL DEFAULT SYSUTCDATETIME(),
    AlertCategory NVARCHAR(40) NOT NULL,
    SeverityCode NVARCHAR(20) NOT NULL,
    LegalEntityCode NVARCHAR(30) NULL,
    NettingSetCode NVARCHAR(30) NULL,
    PledgeCode NVARCHAR(40) NULL,
    AssetId NVARCHAR(40) NULL,
    AlertMessage NVARCHAR(4000) NOT NULL,
    AlertPayload NVARCHAR(MAX) NULL
);

CREATE TABLE #PledgeHierarchy
(
    HierarchyRowId BIGINT IDENTITY(1, 1) PRIMARY KEY,
    PledgeCode NVARCHAR(40) NOT NULL,
    ParentPledgeCode NVARCHAR(40) NULL,
    HierarchyLevel INTEGER NOT NULL,
    HierarchyPath NVARCHAR(4000) NOT NULL
);

CREATE TABLE #SettlementPivotSeed
(
    LegalEntityCode NVARCHAR(30) NOT NULL,
    NettingSetCode NVARCHAR(30) NOT NULL,
    SettlementBucketCode NVARCHAR(20) NOT NULL,
    FunctionalCollateral NUMERIC(19, 4) NOT NULL
);

DECLARE @EntityProfile TABLE
(
    LegalEntityCode NVARCHAR(30) PRIMARY KEY,
    TargetMobilityRatio NUMERIC(19, 4) NOT NULL,
    EscalationBandCode NVARCHAR(20) NOT NULL,
    MaxConcentrationScore INTEGER NOT NULL,
    EntityProfileJson NVARCHAR(MAX) NULL
);

DECLARE @PledgeEdges TABLE
(
    ParentPledgeCode NVARCHAR(40) NOT NULL,
    ChildPledgeCode NVARCHAR(40) NOT NULL,
    TransferCapacity NUMERIC(19, 4) NOT NULL,
    EffectiveUtc DATETIME2(3) NOT NULL,
    PRIMARY KEY (ParentPledgeCode, ChildPledgeCode, EffectiveUtc)
);

DECLARE @InboundCollateral TABLE
(
    FeedRowId INTEGER IDENTITY(1, 1) PRIMARY KEY,
    LegalEntityCode NVARCHAR(30) NOT NULL,
    NettingSetCode NVARCHAR(30) NOT NULL,
    ParentPledgeCode NVARCHAR(40) NULL,
    PledgeCode NVARCHAR(40) NOT NULL,
    AssetId NVARCHAR(40) NOT NULL,
    AssetTypeCode NVARCHAR(20) NOT NULL,
    CurrencyCode CHAR(3) NOT NULL,
    SettlementBucketCode NVARCHAR(20) NOT NULL,
    EligibilityTierCode NVARCHAR(20) NOT NULL,
    CounterpartyCode NVARCHAR(30) NOT NULL,
    SnapshotUtc DATETIME2(3) NOT NULL,
    SettlementDate DATE NOT NULL,
    NominalValue NUMERIC(19, 4) NOT NULL,
    MarketValue NUMERIC(19, 4) NOT NULL,
    PledgedValue NUMERIC(19, 4) NOT NULL,
    RequiredMargin NUMERIC(19, 4) NOT NULL,
    IndependentAmount NUMERIC(19, 4) NOT NULL,
    HaircutPct NUMERIC(9, 4) NOT NULL,
    ConcentrationScore INTEGER NULL,
    RegulatoryFloor NUMERIC(19, 4) NOT NULL,
    PositionJson NVARCHAR(MAX) NULL,
    DiagnosticXml XML NULL
);

INSERT INTO @EntityProfile
(
    LegalEntityCode,
    TargetMobilityRatio,
    EscalationBandCode,
    MaxConcentrationScore,
    EntityProfileJson
)
VALUES
    (N'LE-ALPHA', 1.1500, N'BAND1', 68, N'{"ops":"london","intradayWindow":"europe","priority":"govies"}'),
    (N'LE-BETA', 1.0800, N'BAND2', 61, N'{"ops":"newyork","intradayWindow":"americas","priority":"credit"}'),
    (N'LE-GAMMA', 1.0200, N'BAND3', 57, N'{"ops":"singapore","intradayWindow":"apac","priority":"equities"}');

INSERT INTO @PledgeEdges
(
    ParentPledgeCode,
    ChildPledgeCode,
    TransferCapacity,
    EffectiveUtc
)
VALUES
    (N'PLG-ROOT-100', N'PLG-CHILD-101', 95.0000, '2025-01-01T00:00:00'),
    (N'PLG-ROOT-100', N'PLG-CHILD-102', 75.0000, '2025-01-01T00:00:00'),
    (N'PLG-ROOT-500', N'PLG-CHILD-501', 88.0000, '2025-01-01T00:00:00'),
    (N'PLG-ROOT-500', N'PLG-CHILD-502', 52.0000, '2025-01-01T00:00:00');

INSERT INTO @InboundCollateral
(
    LegalEntityCode,
    NettingSetCode,
    ParentPledgeCode,
    PledgeCode,
    AssetId,
    AssetTypeCode,
    CurrencyCode,
    SettlementBucketCode,
    EligibilityTierCode,
    CounterpartyCode,
    SnapshotUtc,
    SettlementDate,
    NominalValue,
    MarketValue,
    PledgedValue,
    RequiredMargin,
    IndependentAmount,
    HaircutPct,
    ConcentrationScore,
    RegulatoryFloor,
    PositionJson,
    DiagnosticXml
)
VALUES
    (
        N'LE-ALPHA',
        N'CSA-EUR-01',
        NULL,
        N'PLG-ROOT-100',
        N'ISIN-EU-AAA-001',
        N'GOV_BOND',
        N'EUR',
        N'T0',
        N'TIER1',
        N'CP-OMEGA',
        '2025-12-17T07:30:00',
        '2025-12-17',
        900.0000,
        870.0000,
        240.0000,
        690.0000,
        35.0000,
        5.2000,
        73,
        1.1500,
        N'{"priority":"critical","opsOwner":"sofia","mobility":{"substitution":true,"buffer":14},"settlement":{"manual":false}}',
        '<diag><event code="MARGIN_GAP" severity="CRITICAL" /><event code="CONCENTRATION" severity="HIGH" /></diag>'
    ),
    (
        N'LE-ALPHA',
        N'CSA-EUR-01',
        N'PLG-ROOT-100',
        N'PLG-CHILD-101',
        N'ISIN-EU-BILL-010',
        N'T_BILL',
        N'EUR',
        N'T1',
        N'TIER1',
        N'CP-OMEGA',
        '2025-12-17T07:30:00',
        '2025-12-18',
        210.0000,
        205.0000,
        70.0000,
        120.0000,
        10.0000,
        1.6000,
        58,
        1.1200,
        N'{"priority":"high","opsOwner":"sofia","mobility":{"substitution":true,"buffer":6},"settlement":{"manual":false}}',
        '<diag><event code="ROLL_PRESSURE" severity="MEDIUM" /></diag>'
    ),
    (
        N'LE-BETA',
        N'CSA-USD-77',
        NULL,
        N'PLG-ROOT-500',
        N'CUSIP-US-CRD-777',
        N'CORP_BOND',
        N'USD',
        N'T0',
        N'TIER2',
        N'CP-SIGMA',
        '2025-12-17T07:30:00',
        '2025-12-17',
        640.0000,
        602.0000,
        205.0000,
        545.0000,
        42.0000,
        12.4000,
        64,
        1.0800,
        N'{"priority":"critical","opsOwner":"maria","mobility":{"substitution":false,"buffer":9},"settlement":{"manual":true}}',
        '<diag><event code="DEPTH_BREACH" severity="HIGH" /><event code="SETTLEMENT_STRESS" severity="CRITICAL" /></diag>'
    ),
    (
        N'LE-GAMMA',
        N'CSA-USD-99',
        NULL,
        N'PLG-ROOT-901',
        N'TICKER-ETF-009',
        N'EQUITY_ETF',
        N'USD',
        N'T2',
        N'TIER3',
        N'CP-TAU',
        '2025-12-17T07:30:00',
        '2025-12-19',
        390.0000,
        372.0000,
        150.0000,
        188.0000,
        12.0000,
        18.0000,
        50,
        1.0200,
        N'{"priority":"medium","opsOwner":"lee","mobility":{"substitution":true,"buffer":2},"settlement":{"manual":false}}',
        '<diag><event code="NORMAL" severity="INFO" /></diag>'
    );

INSERT INTO #CollateralPositionStage
(
    LegalEntityCode,
    NettingSetCode,
    ParentPledgeCode,
    PledgeCode,
    AssetId,
    AssetTypeCode,
    CurrencyCode,
    SettlementBucketCode,
    EligibilityTierCode,
    CounterpartyCode,
    SnapshotUtc,
    SettlementDate,
    NominalValue,
    MarketValue,
    PledgedValue,
    RequiredMargin,
    IndependentAmount,
    HaircutPct,
    ConcentrationScore,
    RegulatoryFloor,
    PositionJson,
    DiagnosticXml
)
SELECT
    c.LegalEntityCode,
    c.NettingSetCode,
    c.ParentPledgeCode,
    c.PledgeCode,
    c.AssetId,
    c.AssetTypeCode,
    c.CurrencyCode,
    c.SettlementBucketCode,
    c.EligibilityTierCode,
    c.CounterpartyCode,
    c.SnapshotUtc,
    c.SettlementDate,
    c.NominalValue,
    c.MarketValue,
    c.PledgedValue,
    c.RequiredMargin,
    c.IndependentAmount,
    c.HaircutPct,
    c.ConcentrationScore,
    c.RegulatoryFloor,
    c.PositionJson,
    c.DiagnosticXml
FROM @InboundCollateral AS c;

BEGIN TRY
    BEGIN TRANSACTION;
    SAVE TRANSACTION BeforeCollateralEvaluation;

    WITH PledgeTree AS
    (
        SELECT
            c.PledgeCode,
            c.ParentPledgeCode,
            0 AS HierarchyLevel,
            CAST(CONCAT(c.PledgeCode, N'>') AS NVARCHAR(4000)) AS HierarchyPath
        FROM #CollateralPositionStage AS c
        WHERE c.ParentPledgeCode IS NULL

        UNION ALL

        SELECT
            ch.PledgeCode,
            ch.ParentPledgeCode,
            pt.HierarchyLevel + 1,
            CAST(pt.HierarchyPath + ch.PledgeCode + N'>' AS NVARCHAR(4000))
        FROM #CollateralPositionStage AS ch
        INNER JOIN PledgeTree AS pt
            ON ch.ParentPledgeCode = pt.PledgeCode
    )
    INSERT INTO #PledgeHierarchy
    (
        PledgeCode,
        ParentPledgeCode,
        HierarchyLevel,
        HierarchyPath
    )
    SELECT
        pt.PledgeCode,
        pt.ParentPledgeCode,
        pt.HierarchyLevel,
        pt.HierarchyPath
    FROM PledgeTree AS pt
    OPTION (MAXRECURSION 100);

    WITH PositionEnrichment AS
    (
        SELECT
            c.StageCollateralId,
            c.LegalEntityCode,
            c.NettingSetCode,
            c.PledgeCode,
            c.AssetId,
            c.AssetTypeCode,
            c.CurrencyCode,
            c.SettlementBucketCode,
            c.EligibilityTierCode,
            c.CounterpartyCode,
            c.SnapshotUtc,
            c.MarketValue,
            c.PledgedValue,
            c.RequiredMargin,
            c.IndependentAmount,
            c.HaircutPct,
            c.ConcentrationScore,
            c.RegulatoryFloor,
            c.MobilityRatio,
            ep.TargetMobilityRatio,
            ep.EscalationBandCode,
            ep.MaxConcentrationScore,
            ISNULL(JSON_QUERY(c.PositionJson, '$.priority'), JSON_VALUE(c.PositionJson, '$.priority')) AS PriorityCode,
            TRY_CAST(ISNULL(JSON_QUERY(c.PositionJson, '$.mobility.substitution'), JSON_VALUE(c.PositionJson, '$.mobility.substitution')) AS BIT) AS IsSubstitutable,
            TRY_CAST(ISNULL(JSON_QUERY(c.PositionJson, '$.mobility.buffer'), JSON_VALUE(c.PositionJson, '$.mobility.buffer')) AS NUMERIC(19, 4)) AS MobilityBuffer,
            TRY_CAST(ISNULL(JSON_QUERY(c.PositionJson, '$.settlement.manual'), JSON_VALUE(c.PositionJson, '$.settlement.manual')) AS BIT) AS IsManualSettlement,
            ph.HierarchyLevel,
            ph.HierarchyPath,
            DENSE_RANK() OVER (PARTITION BY c.LegalEntityCode, c.NettingSetCode ORDER BY c.MobilityRatio ASC, c.SnapshotUtc DESC) AS MobilityStressRank,
            SUM(c.RequiredMargin) OVER (PARTITION BY c.LegalEntityCode, c.NettingSetCode, c.SettlementBucketCode) AS TotalMarginByBucket
        FROM #CollateralPositionStage AS c
        INNER JOIN @EntityProfile AS ep
            ON ep.LegalEntityCode = c.LegalEntityCode
        LEFT JOIN #PledgeHierarchy AS ph
            ON ph.PledgeCode = c.PledgeCode
    ),
    PledgeExpansion AS
    (
        SELECT
            pe.PledgeCode AS RootPledgeCode,
            pe.PledgeCode AS CurrentPledgeCode,
            CAST(0.0000 AS NUMERIC(19, 4)) AS TransferCapacityUsed,
            0 AS PledgeLevel,
            CAST(pe.PledgeCode + N'>' AS NVARCHAR(4000)) AS PledgePath
        FROM PositionEnrichment AS pe

        UNION ALL

        SELECT
            px.RootPledgeCode,
            e.ChildPledgeCode,
            CAST(px.TransferCapacityUsed + e.TransferCapacity AS NUMERIC(19, 4)),
            px.PledgeLevel + 1,
            CAST(px.PledgePath + e.ChildPledgeCode + N'>' AS NVARCHAR(4000))
        FROM PledgeExpansion AS px
        INNER JOIN @PledgeEdges AS e
            ON e.ParentPledgeCode = px.CurrentPledgeCode
        WHERE px.PledgeLevel < 5
    ),
    MarginSignals AS
    (
        SELECT
            pe.StageCollateralId,
            pe.LegalEntityCode,
            pe.NettingSetCode,
            pe.PledgeCode,
            pe.AssetId,
            pe.PriorityCode,
            pe.EscalationBandCode,
            pe.TargetMobilityRatio,
            pe.MaxConcentrationScore,
            pe.IsSubstitutable,
            pe.MobilityBuffer,
            pe.IsManualSettlement,
            pe.MobilityRatio,
            pe.RegulatoryFloor,
            pe.ConcentrationScore,
            pe.TotalMarginByBucket,
            pe.MobilityStressRank,
            COUNT(*) AS ReachablePledgeEdges,
            MAX(px.PledgeLevel) AS MaxPledgeDepth,
            CASE
                WHEN pe.MobilityRatio < pe.RegulatoryFloor AND pe.PriorityCode = N'critical' THEN N'CRITICAL_MARGIN_BREACH'
                WHEN pe.MobilityRatio < pe.TargetMobilityRatio AND pe.IsManualSettlement = 1 THEN N'MANUAL_SETTLEMENT_GAP'
                WHEN pe.ConcentrationScore > pe.MaxConcentrationScore THEN N'CONCENTRATION_LIMIT_BREACH'
                WHEN pe.TotalMarginByBucket > 650.0000 AND pe.IsSubstitutable = 0 THEN N'BUCKET_CONCENTRATION_BREACH'
                ELSE N'NORMAL'
            END AS SignalCode
        FROM PositionEnrichment AS pe
        LEFT JOIN PledgeExpansion AS px
            ON px.RootPledgeCode = pe.PledgeCode
        GROUP BY
            pe.StageCollateralId,
            pe.LegalEntityCode,
            pe.NettingSetCode,
            pe.PledgeCode,
            pe.AssetId,
            pe.PriorityCode,
            pe.EscalationBandCode,
            pe.TargetMobilityRatio,
            pe.MaxConcentrationScore,
            pe.IsSubstitutable,
            pe.MobilityBuffer,
            pe.IsManualSettlement,
            pe.MobilityRatio,
            pe.RegulatoryFloor,
            pe.ConcentrationScore,
            pe.TotalMarginByBucket,
            pe.MobilityStressRank
    )
    INSERT INTO #MarginAlertQueue
    (
        AlertCategory,
        SeverityCode,
        LegalEntityCode,
        NettingSetCode,
        PledgeCode,
        AssetId,
        AlertMessage,
        AlertPayload
    )
    SELECT
        N'COLLATERAL_SIGNAL',
        CASE
            WHEN s.SignalCode IN (N'CRITICAL_MARGIN_BREACH', N'MANUAL_SETTLEMENT_GAP') THEN N'CRITICAL'
            WHEN s.SignalCode IN (N'CONCENTRATION_LIMIT_BREACH', N'BUCKET_CONCENTRATION_BREACH') THEN N'HIGH'
            ELSE N'MEDIUM'
        END,
        s.LegalEntityCode,
        s.NettingSetCode,
        s.PledgeCode,
        s.AssetId,
        CONCAT(N'Collateral signal detected for pledge ', s.PledgeCode, N': ', s.SignalCode),
        (
            SELECT
                s.PriorityCode AS [priority],
                s.EscalationBandCode AS [escalationBand],
                s.MobilityRatio AS [mobilityRatio],
                s.RegulatoryFloor AS [regulatoryFloor],
                s.ConcentrationScore AS [concentrationScore],
                s.TotalMarginByBucket AS [totalMarginByBucket],
                s.ReachablePledgeEdges AS [reachablePledgeEdges],
                s.MaxPledgeDepth AS [maxPledgeDepth]
            FOR JSON PATH, ROOT('collateralAlert'), INCLUDE_NULL_VALUES
        )
    FROM MarginSignals AS s
    WHERE s.SignalCode <> N'NORMAL';

    INSERT INTO #SettlementPivotSeed
    (
        LegalEntityCode,
        NettingSetCode,
        SettlementBucketCode,
        FunctionalCollateral
    )
    SELECT
        c.LegalEntityCode,
        c.NettingSetCode,
        c.SettlementBucketCode,
        (c.MarketValue - c.PledgedValue) - c.RequiredMargin + c.IndependentAmount
    FROM #CollateralPositionStage AS c;

    DECLARE @PivotColumns NVARCHAR(MAX);
    DECLARE @PivotSql NVARCHAR(MAX);

    SELECT
        @PivotColumns = STRING_AGG(QUOTENAME(SettlementBucketCode), N',')
    FROM
    (
        SELECT DISTINCT SettlementBucketCode
        FROM #SettlementPivotSeed
    ) AS settlement_buckets;

    SET @PivotSql = N'
        SELECT LegalEntityCode, NettingSetCode, ' + @PivotColumns + N'
        INTO #SettlementMobilityMatrix
        FROM
        (
            SELECT LegalEntityCode, NettingSetCode, SettlementBucketCode, FunctionalCollateral
            FROM #SettlementPivotSeed
        ) src
        PIVOT
        (
            SUM(FunctionalCollateral)
            FOR SettlementBucketCode IN (' + @PivotColumns + N')
        ) p;';

    EXEC sys.sp_executesql @PivotSql;

    MERGE INTO dbo.CollateralMobilitySnapshot AS target
    USING
    (
        SELECT
            c.LegalEntityCode,
            c.NettingSetCode,
            COUNT(*) AS PositionCount,
            SUM(c.MarketValue) AS TotalMarketValue,
            SUM(c.RequiredMargin) AS TotalRequiredMargin,
            AVG(c.MobilityRatio) AS AvgMobilityRatio,
            MAX(c.SnapshotUtc) AS LastSnapshotUtc,
            SYSUTCDATETIME() AS RefreshUtc
        FROM #CollateralPositionStage AS c
        GROUP BY
            c.LegalEntityCode,
            c.NettingSetCode
    ) AS source
        ON target.LegalEntityCode = source.LegalEntityCode
       AND target.NettingSetCode = source.NettingSetCode
    WHEN MATCHED THEN
        UPDATE SET
            target.PositionCount = source.PositionCount,
            target.TotalMarketValue = source.TotalMarketValue,
            target.TotalRequiredMargin = source.TotalRequiredMargin,
            target.AvgMobilityRatio = source.AvgMobilityRatio,
            target.LastSnapshotUtc = source.LastSnapshotUtc,
            target.LastRefreshUtc = source.RefreshUtc
    WHEN NOT MATCHED THEN
        INSERT
        (
            LegalEntityCode,
            NettingSetCode,
            PositionCount,
            TotalMarketValue,
            TotalRequiredMargin,
            AvgMobilityRatio,
            LastSnapshotUtc,
            LastRefreshUtc
        )
        VALUES
        (
            source.LegalEntityCode,
            source.NettingSetCode,
            source.PositionCount,
            source.TotalMarketValue,
            source.TotalRequiredMargin,
            source.AvgMobilityRatio,
            source.LastSnapshotUtc,
            source.RefreshUtc
        )
    OUTPUT
        $action,
        inserted.LegalEntityCode,
        inserted.NettingSetCode,
        inserted.LastRefreshUtc
    INTO dbo.CollateralMobilityAudit
    (
        MergeAction,
        LegalEntityCode,
        NettingSetCode,
        AuditUtc
    );

    IF EXISTS
    (
        SELECT 1
        FROM #MarginAlertQueue
        WHERE SeverityCode = N'CRITICAL'
    )
    BEGIN
        WAITFOR TIME '23:59:59';
    END;

    DECLARE @DispatchLegalEntityCode AS NVARCHAR(30);
    DECLARE @DispatchNettingSetCode AS NVARCHAR(30);
    DECLARE @DispatchPledgeCode AS NVARCHAR(40);

    DECLARE CollateralDispatchCursor CURSOR LOCAL FAST_FORWARD FOR
        SELECT
            q.LegalEntityCode,
            q.NettingSetCode,
            q.PledgeCode
        FROM #MarginAlertQueue AS q
        WHERE q.SeverityCode IN (N'CRITICAL', N'HIGH')
        ORDER BY q.AlertUtc, q.AlertId;

    OPEN CollateralDispatchCursor;
    FETCH NEXT FROM CollateralDispatchCursor
        INTO @DispatchLegalEntityCode, @DispatchNettingSetCode, @DispatchPledgeCode;

    WHILE @@FETCH_STATUS = 0
    BEGIN
        EXEC dbo.usp_DispatchCollateralEscalation
            @LegalEntityCode = @DispatchLegalEntityCode,
            @NettingSetCode = @DispatchNettingSetCode,
            @PledgeCode = @DispatchPledgeCode,
            @RequestedUtc = SYSUTCDATETIME();

        FETCH NEXT FROM CollateralDispatchCursor
            INTO @DispatchLegalEntityCode, @DispatchNettingSetCode, @DispatchPledgeCode;
    END;

    CLOSE CollateralDispatchCursor;
    DEALLOCATE CollateralDispatchCursor;

    INSERT INTO dbo.CollateralMobilityRuns
    (
        RunUtc,
        RunCategory,
        FinalStateCode,
        AlertEnvelopeJson,
        PledgeEnvelopeXml
    )
    SELECT
        SYSUTCDATETIME(),
        N'COLLATERAL_MOBILITY',
        CASE
            WHEN EXISTS (SELECT 1 FROM #MarginAlertQueue WHERE SeverityCode = N'CRITICAL') THEN N'ESCALATED'
            WHEN EXISTS (SELECT 1 FROM #MarginAlertQueue) THEN N'WARNINGS'
            ELSE N'CLEAR'
        END,
        (
            SELECT
                q.AlertCategory,
                q.SeverityCode,
                q.LegalEntityCode,
                q.NettingSetCode,
                q.PledgeCode,
                q.AssetId,
                q.AlertMessage
            FROM #MarginAlertQueue AS q
            FOR JSON PATH, ROOT('alerts'), INCLUDE_NULL_VALUES
        ),
        (
            SELECT
                h.PledgeCode AS [@pledgeCode],
                h.ParentPledgeCode AS [@parentPledgeCode],
                h.HierarchyLevel AS [@level],
                h.HierarchyPath AS [path]
            FROM #PledgeHierarchy AS h
            FOR XML PATH('pledge'), ROOT('pledges'), TYPE
        );

    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    IF CURSOR_STATUS('local', 'CollateralDispatchCursor') >= -1
    BEGIN
        CLOSE CollateralDispatchCursor;
        DEALLOCATE CollateralDispatchCursor;
    END;

    IF XACT_STATE() = -1
        ROLLBACK TRANSACTION;
    ELSE IF XACT_STATE() = 1
        ROLLBACK TRANSACTION BeforeCollateralEvaluation;

    INSERT INTO #MarginAlertQueue
    (
        AlertCategory,
        SeverityCode,
        LegalEntityCode,
        NettingSetCode,
        PledgeCode,
        AssetId,
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
    q.LegalEntityCode,
    q.NettingSetCode,
    q.PledgeCode,
    q.AssetId,
    q.AlertMessage,
    q.AlertPayload
FROM #MarginAlertQueue AS q
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
    h.PledgeCode,
    h.ParentPledgeCode,
    h.HierarchyLevel,
    h.HierarchyPath
FROM #PledgeHierarchy AS h
ORDER BY
    h.PledgeCode,
    h.HierarchyLevel;

DROP TABLE IF EXISTS #SettlementMobilityMatrix;
DROP TABLE IF EXISTS #SettlementPivotSeed;
DROP TABLE IF EXISTS #PledgeHierarchy;
DROP TABLE IF EXISTS #MarginAlertQueue;
DROP TABLE IF EXISTS #CollateralPositionStage;
GO

EXEC dbo.usp_FinalizeCollateralMobilityWindow
    @WindowCode = N'GLOBAL_COLLATERAL_MOBILITY',
    @ClosedUtc = SYSUTCDATETIME(),
    @ClosedBy = ORIGINAL_LOGIN();
