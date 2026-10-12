/* Extreme T-SQL stress sample 6 */
/* Purpose: portfolio liquidity command-center workflow with recursive funding trees, */
/* reserve breaches, ladder pivots, XML/JSON envelopes, savepoints, dynamic SQL, */
/* queue dispatch, and procedural exception recovery. */

SET NOCOUNT ON;
SET XACT_ABORT ON;
SET DEADLOCK_PRIORITY HIGH;

DROP TABLE IF EXISTS #LiquidityPositionStage;
DROP TABLE IF EXISTS #LiquidityAlertQueue;
DROP TABLE IF EXISTS #FundingHierarchy;
DROP TABLE IF EXISTS #BucketPivotSeed;

CREATE TABLE #LiquidityPositionStage
(
    StagePositionId BIGINT IDENTITY(1, 1) PRIMARY KEY,
    LoadBatchId UNIQUEIDENTIFIER NOT NULL DEFAULT NEWID(),
    PortfolioCode NVARCHAR(30) NOT NULL,
    DeskCode NVARCHAR(30) NOT NULL,
    ParentPositionCode NVARCHAR(40) NULL,
    PositionCode NVARCHAR(40) NOT NULL,
    InstrumentCode NVARCHAR(40) NOT NULL,
    CurrencyCode CHAR(3) NOT NULL,
    MaturityBucketCode NVARCHAR(20) NOT NULL,
    LiquidityTierCode NVARCHAR(20) NOT NULL,
    FundingSourceCode NVARCHAR(20) NOT NULL,
    SnapshotUtc DATETIME2(3) NOT NULL,
    SettlementDate DATE NOT NULL,
    MarketValue NUMERIC(19, 4) NOT NULL,
    EncumberedValue NUMERIC(19, 4) NOT NULL,
    UnsecuredOutflow NUMERIC(19, 4) NOT NULL,
    SecuredInflow NUMERIC(19, 4) NOT NULL,
    StressHaircutPct NUMERIC(9, 4) NOT NULL,
    MarketDepthScore INTEGER NULL,
    RegulatoryMinRatio NUMERIC(19, 4) NOT NULL,
    LiquidityRatio AS (
        CASE
            WHEN UnsecuredOutflow = 0 THEN 0
            ELSE ((MarketValue - EncumberedValue) * (1 - (StressHaircutPct / 100.0))) / NULLIF(UnsecuredOutflow, 0)
        END
    ) PERSISTED,
    PositionJson NVARCHAR(MAX) NULL,
    DiagnosticXml XML NULL,
    CreatedUtc DATETIME2(3) NOT NULL DEFAULT SYSUTCDATETIME()
);

CREATE TABLE #LiquidityAlertQueue
(
    AlertId BIGINT IDENTITY(1, 1) PRIMARY KEY,
    AlertUtc DATETIME2(3) NOT NULL DEFAULT SYSUTCDATETIME(),
    AlertCategory NVARCHAR(40) NOT NULL,
    SeverityCode NVARCHAR(20) NOT NULL,
    PortfolioCode NVARCHAR(30) NULL,
    DeskCode NVARCHAR(30) NULL,
    PositionCode NVARCHAR(40) NULL,
    InstrumentCode NVARCHAR(40) NULL,
    AlertMessage NVARCHAR(4000) NOT NULL,
    AlertPayload NVARCHAR(MAX) NULL
);

CREATE TABLE #FundingHierarchy
(
    HierarchyRowId BIGINT IDENTITY(1, 1) PRIMARY KEY,
    PositionCode NVARCHAR(40) NOT NULL,
    ParentPositionCode NVARCHAR(40) NULL,
    HierarchyLevel INTEGER NOT NULL,
    HierarchyPath NVARCHAR(4000) NOT NULL
);

CREATE TABLE #BucketPivotSeed
(
    PortfolioCode NVARCHAR(30) NOT NULL,
    DeskCode NVARCHAR(30) NOT NULL,
    MaturityBucketCode NVARCHAR(20) NOT NULL,
    FunctionalLiquidity NUMERIC(19, 4) NOT NULL
);

DECLARE @PortfolioProfile TABLE
(
    PortfolioCode NVARCHAR(30) PRIMARY KEY,
    TargetLiquidityRatio NUMERIC(19, 4) NOT NULL,
    EscalationBandCode NVARCHAR(20) NOT NULL,
    MaxMarketDepthScore INTEGER NOT NULL,
    PortfolioProfileJson NVARCHAR(MAX) NULL
);

DECLARE @FundingEdges TABLE
(
    ParentPositionCode NVARCHAR(40) NOT NULL,
    ChildPositionCode NVARCHAR(40) NOT NULL,
    TransferCapacity NUMERIC(19, 4) NOT NULL,
    EffectiveUtc DATETIME2(3) NOT NULL,
    PRIMARY KEY (ParentPositionCode, ChildPositionCode, EffectiveUtc)
);

DECLARE @InboundPositions TABLE
(
    FeedRowId INTEGER IDENTITY(1, 1) PRIMARY KEY,
    PortfolioCode NVARCHAR(30) NOT NULL,
    DeskCode NVARCHAR(30) NOT NULL,
    ParentPositionCode NVARCHAR(40) NULL,
    PositionCode NVARCHAR(40) NOT NULL,
    InstrumentCode NVARCHAR(40) NOT NULL,
    CurrencyCode CHAR(3) NOT NULL,
    MaturityBucketCode NVARCHAR(20) NOT NULL,
    LiquidityTierCode NVARCHAR(20) NOT NULL,
    FundingSourceCode NVARCHAR(20) NOT NULL,
    SnapshotUtc DATETIME2(3) NOT NULL,
    SettlementDate DATE NOT NULL,
    MarketValue NUMERIC(19, 4) NOT NULL,
    EncumberedValue NUMERIC(19, 4) NOT NULL,
    UnsecuredOutflow NUMERIC(19, 4) NOT NULL,
    SecuredInflow NUMERIC(19, 4) NOT NULL,
    StressHaircutPct NUMERIC(9, 4) NOT NULL,
    MarketDepthScore INTEGER NULL,
    RegulatoryMinRatio NUMERIC(19, 4) NOT NULL,
    PositionJson NVARCHAR(MAX) NULL,
    DiagnosticXml XML NULL
);

INSERT INTO @PortfolioProfile
(
    PortfolioCode,
    TargetLiquidityRatio,
    EscalationBandCode,
    MaxMarketDepthScore,
    PortfolioProfileJson
)
VALUES
    (N'PORT-ALPHA', 1.2000, N'LEVEL1', 70, N'{"treasury":"emea","intradayLimit":250,"priority":"government"}'),
    (N'PORT-BETA', 1.1000, N'LEVEL2', 60, N'{"treasury":"americas","intradayLimit":180,"priority":"credit"}'),
    (N'PORT-GAMMA', 1.0500, N'LEVEL3', 55, N'{"treasury":"apac","intradayLimit":160,"priority":"equity"}');

INSERT INTO @FundingEdges
(
    ParentPositionCode,
    ChildPositionCode,
    TransferCapacity,
    EffectiveUtc
)
VALUES
    (N'POS-ROOT-001', N'POS-CHILD-101', 140.0000, '2025-01-01T00:00:00'),
    (N'POS-ROOT-001', N'POS-CHILD-102', 90.0000, '2025-01-01T00:00:00'),
    (N'POS-ROOT-777', N'POS-CHILD-701', 110.0000, '2025-01-01T00:00:00'),
    (N'POS-ROOT-777', N'POS-CHILD-702', 86.0000, '2025-01-01T00:00:00');

INSERT INTO @InboundPositions
(
    PortfolioCode,
    DeskCode,
    ParentPositionCode,
    PositionCode,
    InstrumentCode,
    CurrencyCode,
    MaturityBucketCode,
    LiquidityTierCode,
    FundingSourceCode,
    SnapshotUtc,
    SettlementDate,
    MarketValue,
    EncumberedValue,
    UnsecuredOutflow,
    SecuredInflow,
    StressHaircutPct,
    MarketDepthScore,
    RegulatoryMinRatio,
    PositionJson,
    DiagnosticXml
)
VALUES
    (
        N'PORT-ALPHA',
        N'RATES',
        NULL,
        N'POS-ROOT-001',
        N'BOND-GOV-10Y',
        N'EUR',
        N'D0-D7',
        N'HQLA1',
        N'CBANK',
        '2025-12-15T08:00:00',
        '2025-12-16',
        840.0000,
        120.0000,
        710.0000,
        35.0000,
        4.5000,
        74,
        1.2000,
        N'{"priority":"critical","deskOwner":"anna","collateral":{"rehypothecation":false,"buffer":18},"funding":{"callable":true}}',
        '<diag><event code="RATIO_PRESSURE" severity="CRITICAL" /><event code="DEPTH_SLIPPAGE" severity="HIGH" /></diag>'
    ),
    (
        N'PORT-ALPHA',
        N'RATES',
        N'POS-ROOT-001',
        N'POS-CHILD-101',
        N'BILL-GOV-3M',
        N'EUR',
        N'D8-D30',
        N'HQLA1',
        N'REPO',
        '2025-12-15T08:00:00',
        '2025-12-20',
        220.0000,
        40.0000,
        95.0000,
        18.0000,
        2.0000,
        61,
        1.1000,
        N'{"priority":"high","deskOwner":"anna","collateral":{"rehypothecation":true,"buffer":7},"funding":{"callable":false}}',
        '<diag><event code="ROLL_RISK" severity="MEDIUM" /></diag>'
    ),
    (
        N'PORT-BETA',
        N'CREDIT',
        NULL,
        N'POS-ROOT-777',
        N'BOND-CORP-5Y',
        N'USD',
        N'D0-D7',
        N'HQLA2',
        N'CP',
        '2025-12-15T08:00:00',
        '2025-12-16',
        610.0000,
        180.0000,
        520.0000,
        42.0000,
        11.5000,
        58,
        1.1000,
        N'{"priority":"critical","deskOwner":"marc","collateral":{"rehypothecation":false,"buffer":10},"funding":{"callable":true}}',
        '<diag><event code="HAIRCUT_RISE" severity="HIGH" /><event code="OUTFLOW_SPIKE" severity="CRITICAL" /></diag>'
    ),
    (
        N'PORT-GAMMA',
        N'EQUITY',
        NULL,
        N'POS-ROOT-901',
        N'EQ-ETF-CORE',
        N'USD',
        N'D31-D90',
        N'NON_HQLA',
        N'PRIME',
        '2025-12-15T08:00:00',
        '2026-01-14',
        470.0000,
        150.0000,
        180.0000,
        16.0000,
        19.0000,
        49,
        1.0500,
        N'{"priority":"medium","deskOwner":"lin","collateral":{"rehypothecation":true,"buffer":3},"funding":{"callable":false}}',
        '<diag><event code="NORMAL" severity="INFO" /></diag>'
    );

INSERT INTO #LiquidityPositionStage
(
    PortfolioCode,
    DeskCode,
    ParentPositionCode,
    PositionCode,
    InstrumentCode,
    CurrencyCode,
    MaturityBucketCode,
    LiquidityTierCode,
    FundingSourceCode,
    SnapshotUtc,
    SettlementDate,
    MarketValue,
    EncumberedValue,
    UnsecuredOutflow,
    SecuredInflow,
    StressHaircutPct,
    MarketDepthScore,
    RegulatoryMinRatio,
    PositionJson,
    DiagnosticXml
)
SELECT
    p.PortfolioCode,
    p.DeskCode,
    p.ParentPositionCode,
    p.PositionCode,
    p.InstrumentCode,
    p.CurrencyCode,
    p.MaturityBucketCode,
    p.LiquidityTierCode,
    p.FundingSourceCode,
    p.SnapshotUtc,
    p.SettlementDate,
    p.MarketValue,
    p.EncumberedValue,
    p.UnsecuredOutflow,
    p.SecuredInflow,
    p.StressHaircutPct,
    p.MarketDepthScore,
    p.RegulatoryMinRatio,
    p.PositionJson,
    p.DiagnosticXml
FROM @InboundPositions AS p;

BEGIN TRY
    BEGIN TRANSACTION;
    SAVE TRANSACTION BeforeLiquidityEvaluation;

    WITH PositionTree AS
    (
        SELECT
            p.PositionCode,
            p.ParentPositionCode,
            0 AS HierarchyLevel,
            CAST(CONCAT(p.PositionCode, N'>') AS NVARCHAR(4000)) AS HierarchyPath
        FROM #LiquidityPositionStage AS p
        WHERE p.ParentPositionCode IS NULL

        UNION ALL

        SELECT
            c.PositionCode,
            c.ParentPositionCode,
            pt.HierarchyLevel + 1,
            CAST(pt.HierarchyPath + c.PositionCode + N'>' AS NVARCHAR(4000))
        FROM #LiquidityPositionStage AS c
        INNER JOIN PositionTree AS pt
            ON c.ParentPositionCode = pt.PositionCode
    )
    INSERT INTO #FundingHierarchy
    (
        PositionCode,
        ParentPositionCode,
        HierarchyLevel,
        HierarchyPath
    )
    SELECT
        pt.PositionCode,
        pt.ParentPositionCode,
        pt.HierarchyLevel,
        pt.HierarchyPath
    FROM PositionTree AS pt
    OPTION (MAXRECURSION 100);

    WITH PositionEnrichment AS
    (
        SELECT
            p.StagePositionId,
            p.PortfolioCode,
            p.DeskCode,
            p.PositionCode,
            p.InstrumentCode,
            p.CurrencyCode,
            p.MaturityBucketCode,
            p.LiquidityTierCode,
            p.FundingSourceCode,
            p.SnapshotUtc,
            p.MarketValue,
            p.EncumberedValue,
            p.UnsecuredOutflow,
            p.SecuredInflow,
            p.StressHaircutPct,
            p.MarketDepthScore,
            p.RegulatoryMinRatio,
            p.LiquidityRatio,
            pp.TargetLiquidityRatio,
            pp.EscalationBandCode,
            pp.MaxMarketDepthScore,
            ISNULL(JSON_QUERY(p.PositionJson, '$.priority'), JSON_VALUE(p.PositionJson, '$.priority')) AS PriorityCode,
            TRY_CAST(ISNULL(JSON_QUERY(p.PositionJson, '$.collateral.rehypothecation'), JSON_VALUE(p.PositionJson, '$.collateral.rehypothecation')) AS BIT) AS IsRehypothecatable,
            TRY_CAST(ISNULL(JSON_QUERY(p.PositionJson, '$.collateral.buffer'), JSON_VALUE(p.PositionJson, '$.collateral.buffer')) AS NUMERIC(19, 4)) AS CollateralBuffer,
            TRY_CAST(ISNULL(JSON_QUERY(p.PositionJson, '$.funding.callable'), JSON_VALUE(p.PositionJson, '$.funding.callable')) AS BIT) AS IsCallableFunding,
            fh.HierarchyLevel,
            fh.HierarchyPath,
            DENSE_RANK() OVER (PARTITION BY p.PortfolioCode, p.DeskCode ORDER BY p.LiquidityRatio ASC, p.SnapshotUtc DESC) AS LiquidityStressRank,
            SUM(p.UnsecuredOutflow) OVER (PARTITION BY p.PortfolioCode, p.DeskCode, p.MaturityBucketCode) AS TotalOutflowByBucket
        FROM #LiquidityPositionStage AS p
        INNER JOIN @PortfolioProfile AS pp
            ON pp.PortfolioCode = p.PortfolioCode
        LEFT JOIN #FundingHierarchy AS fh
            ON fh.PositionCode = p.PositionCode
    ),
    FundingExpansion AS
    (
        SELECT
            pe.PositionCode AS RootPositionCode,
            pe.PositionCode AS CurrentPositionCode,
            CAST(0.0000 AS NUMERIC(19, 4)) AS TransferCapacityUsed,
            0 AS FundingLevel,
            CAST(pe.PositionCode + N'>' AS NVARCHAR(4000)) AS FundingPath
        FROM PositionEnrichment AS pe

        UNION ALL

        SELECT
            fe.RootPositionCode,
            e.ChildPositionCode,
            CAST(fe.TransferCapacityUsed + e.TransferCapacity AS NUMERIC(19, 4)),
            fe.FundingLevel + 1,
            CAST(fe.FundingPath + e.ChildPositionCode + N'>' AS NVARCHAR(4000))
        FROM FundingExpansion AS fe
        INNER JOIN @FundingEdges AS e
            ON e.ParentPositionCode = fe.CurrentPositionCode
        WHERE fe.FundingLevel < 5
    ),
    LiquiditySignals AS
    (
        SELECT
            pe.StagePositionId,
            pe.PortfolioCode,
            pe.DeskCode,
            pe.PositionCode,
            pe.InstrumentCode,
            pe.PriorityCode,
            pe.EscalationBandCode,
            pe.TargetLiquidityRatio,
            pe.MaxMarketDepthScore,
            pe.IsRehypothecatable,
            pe.CollateralBuffer,
            pe.IsCallableFunding,
            pe.LiquidityRatio,
            pe.RegulatoryMinRatio,
            pe.MarketDepthScore,
            pe.TotalOutflowByBucket,
            pe.LiquidityStressRank,
            COUNT(*) AS ReachableFundingEdges,
            MAX(fe.FundingLevel) AS MaxFundingDepth,
            CASE
                WHEN pe.LiquidityRatio < pe.RegulatoryMinRatio AND pe.PriorityCode = N'critical' THEN N'CRITICAL_REGULATORY_BREACH'
                WHEN pe.LiquidityRatio < pe.TargetLiquidityRatio AND pe.IsCallableFunding = 1 THEN N'CALLABLE_FUNDING_GAP'
                WHEN pe.MarketDepthScore > pe.MaxMarketDepthScore THEN N'MARKET_DEPTH_BREACH'
                WHEN pe.TotalOutflowByBucket > 600.0000 AND pe.IsRehypothecatable = 0 THEN N'OUTFLOW_CONCENTRATION_BREACH'
                ELSE N'NORMAL'
            END AS SignalCode
        FROM PositionEnrichment AS pe
        LEFT JOIN FundingExpansion AS fe
            ON fe.RootPositionCode = pe.PositionCode
        GROUP BY
            pe.StagePositionId,
            pe.PortfolioCode,
            pe.DeskCode,
            pe.PositionCode,
            pe.InstrumentCode,
            pe.PriorityCode,
            pe.EscalationBandCode,
            pe.TargetLiquidityRatio,
            pe.MaxMarketDepthScore,
            pe.IsRehypothecatable,
            pe.CollateralBuffer,
            pe.IsCallableFunding,
            pe.LiquidityRatio,
            pe.RegulatoryMinRatio,
            pe.MarketDepthScore,
            pe.TotalOutflowByBucket,
            pe.LiquidityStressRank
    )
    INSERT INTO #LiquidityAlertQueue
    (
        AlertCategory,
        SeverityCode,
        PortfolioCode,
        DeskCode,
        PositionCode,
        InstrumentCode,
        AlertMessage,
        AlertPayload
    )
    SELECT
        N'LIQUIDITY_SIGNAL',
        CASE
            WHEN s.SignalCode IN (N'CRITICAL_REGULATORY_BREACH', N'CALLABLE_FUNDING_GAP') THEN N'CRITICAL'
            WHEN s.SignalCode IN (N'MARKET_DEPTH_BREACH', N'OUTFLOW_CONCENTRATION_BREACH') THEN N'HIGH'
            ELSE N'MEDIUM'
        END,
        s.PortfolioCode,
        s.DeskCode,
        s.PositionCode,
        s.InstrumentCode,
        CONCAT(N'Liquidity signal detected for position ', s.PositionCode, N': ', s.SignalCode),
        (
            SELECT
                s.PriorityCode AS [priority],
                s.EscalationBandCode AS [escalationBand],
                s.LiquidityRatio AS [liquidityRatio],
                s.RegulatoryMinRatio AS [regulatoryMinRatio],
                s.MarketDepthScore AS [marketDepthScore],
                s.TotalOutflowByBucket AS [totalOutflowByBucket],
                s.ReachableFundingEdges AS [reachableFundingEdges],
                s.MaxFundingDepth AS [maxFundingDepth]
            FOR JSON PATH, ROOT('liquidityAlert'), INCLUDE_NULL_VALUES
        )
    FROM LiquiditySignals AS s
    WHERE s.SignalCode <> N'NORMAL';

    INSERT INTO #BucketPivotSeed
    (
        PortfolioCode,
        DeskCode,
        MaturityBucketCode,
        FunctionalLiquidity
    )
    SELECT
        p.PortfolioCode,
        p.DeskCode,
        p.MaturityBucketCode,
        (p.MarketValue - p.EncumberedValue) - p.UnsecuredOutflow + p.SecuredInflow
    FROM #LiquidityPositionStage AS p;

    DECLARE @PivotColumns NVARCHAR(MAX);
    DECLARE @PivotSql NVARCHAR(MAX);

    SELECT
        @PivotColumns = STRING_AGG(QUOTENAME(MaturityBucketCode), N',')
    FROM
    (
        SELECT DISTINCT MaturityBucketCode
        FROM #BucketPivotSeed
    ) AS bucket_codes;

    SET @PivotSql = N'
        SELECT PortfolioCode, DeskCode, ' + @PivotColumns + N'
        INTO #LiquidityBucketMatrix
        FROM
        (
            SELECT PortfolioCode, DeskCode, MaturityBucketCode, FunctionalLiquidity
            FROM #BucketPivotSeed
        ) src
        PIVOT
        (
            SUM(FunctionalLiquidity)
            FOR MaturityBucketCode IN (' + @PivotColumns + N')
        ) p;';

    EXEC sys.sp_executesql @PivotSql;

    MERGE INTO dbo.PortfolioLiquiditySnapshot AS target
    USING
    (
        SELECT
            p.PortfolioCode,
            p.DeskCode,
            COUNT(*) AS PositionCount,
            SUM(p.MarketValue) AS TotalMarketValue,
            SUM(p.UnsecuredOutflow) AS TotalUnsecuredOutflow,
            AVG(p.LiquidityRatio) AS AvgLiquidityRatio,
            MAX(p.SnapshotUtc) AS LastSnapshotUtc,
            SYSUTCDATETIME() AS RefreshUtc
        FROM #LiquidityPositionStage AS p
        GROUP BY
            p.PortfolioCode,
            p.DeskCode
    ) AS source
        ON target.PortfolioCode = source.PortfolioCode
       AND target.DeskCode = source.DeskCode
    WHEN MATCHED THEN
        UPDATE SET
            target.PositionCount = source.PositionCount,
            target.TotalMarketValue = source.TotalMarketValue,
            target.TotalUnsecuredOutflow = source.TotalUnsecuredOutflow,
            target.AvgLiquidityRatio = source.AvgLiquidityRatio,
            target.LastSnapshotUtc = source.LastSnapshotUtc,
            target.LastRefreshUtc = source.RefreshUtc
    WHEN NOT MATCHED THEN
        INSERT
        (
            PortfolioCode,
            DeskCode,
            PositionCount,
            TotalMarketValue,
            TotalUnsecuredOutflow,
            AvgLiquidityRatio,
            LastSnapshotUtc,
            LastRefreshUtc
        )
        VALUES
        (
            source.PortfolioCode,
            source.DeskCode,
            source.PositionCount,
            source.TotalMarketValue,
            source.TotalUnsecuredOutflow,
            source.AvgLiquidityRatio,
            source.LastSnapshotUtc,
            source.RefreshUtc
        )
    OUTPUT
        $action,
        inserted.PortfolioCode,
        inserted.DeskCode,
        inserted.LastRefreshUtc
    INTO dbo.PortfolioLiquidityAudit
    (
        MergeAction,
        PortfolioCode,
        DeskCode,
        AuditUtc
    );

    IF EXISTS
    (
        SELECT 1
        FROM #LiquidityAlertQueue
        WHERE SeverityCode = N'CRITICAL'
    )
    BEGIN
        WAITFOR DELAY '00:00:02';
    END;

    DECLARE @DispatchPortfolioCode AS NVARCHAR(30);
    DECLARE @DispatchDeskCode AS NVARCHAR(30);
    DECLARE @DispatchPositionCode AS NVARCHAR(40);

    DECLARE LiquidityDispatchCursor CURSOR LOCAL FAST_FORWARD FOR
        SELECT
            q.PortfolioCode,
            q.DeskCode,
            q.PositionCode
        FROM #LiquidityAlertQueue AS q
        WHERE q.SeverityCode IN (N'CRITICAL', N'HIGH')
        ORDER BY q.AlertUtc, q.AlertId;

    OPEN LiquidityDispatchCursor;
    FETCH NEXT FROM LiquidityDispatchCursor
        INTO @DispatchPortfolioCode, @DispatchDeskCode, @DispatchPositionCode;

    WHILE @@FETCH_STATUS = 0
    BEGIN
        EXEC dbo.usp_DispatchLiquidityEscalation
            @PortfolioCode = @DispatchPortfolioCode,
            @DeskCode = @DispatchDeskCode,
            @PositionCode = @DispatchPositionCode,
            @RequestedUtc = SYSUTCDATETIME();

        FETCH NEXT FROM LiquidityDispatchCursor
            INTO @DispatchPortfolioCode, @DispatchDeskCode, @DispatchPositionCode;
    END;

    CLOSE LiquidityDispatchCursor;
    DEALLOCATE LiquidityDispatchCursor;

    INSERT INTO dbo.PortfolioLiquidityRuns
    (
        RunUtc,
        RunCategory,
        FinalStateCode,
        AlertEnvelopeJson,
        FundingEnvelopeXml
    )
    SELECT
        SYSUTCDATETIME(),
        N'PORTFOLIO_LIQUIDITY',
        CASE
            WHEN EXISTS (SELECT 1 FROM #LiquidityAlertQueue WHERE SeverityCode = N'CRITICAL') THEN N'ESCALATED'
            WHEN EXISTS (SELECT 1 FROM #LiquidityAlertQueue) THEN N'WARNINGS'
            ELSE N'CLEAR'
        END,
        (
            SELECT
                q.AlertCategory,
                q.SeverityCode,
                q.PortfolioCode,
                q.DeskCode,
                q.PositionCode,
                q.InstrumentCode,
                q.AlertMessage
            FROM #LiquidityAlertQueue AS q
            FOR JSON PATH, ROOT('alerts'), INCLUDE_NULL_VALUES
        ),
        (
            SELECT
                h.PositionCode AS [@positionCode],
                h.ParentPositionCode AS [@parentPositionCode],
                h.HierarchyLevel AS [@level],
                h.HierarchyPath AS [path]
            FROM #FundingHierarchy AS h
            FOR XML PATH('position'), ROOT('funding'), TYPE
        );

    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    IF CURSOR_STATUS('local', 'LiquidityDispatchCursor') >= -1
    BEGIN
        CLOSE LiquidityDispatchCursor;
        DEALLOCATE LiquidityDispatchCursor;
    END;

    IF XACT_STATE() = -1
        ROLLBACK TRANSACTION;
    ELSE IF XACT_STATE() = 1
        ROLLBACK TRANSACTION BeforeLiquidityEvaluation;

    INSERT INTO #LiquidityAlertQueue
    (
        AlertCategory,
        SeverityCode,
        PortfolioCode,
        DeskCode,
        PositionCode,
        InstrumentCode,
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
    q.PortfolioCode,
    q.DeskCode,
    q.PositionCode,
    q.InstrumentCode,
    q.AlertMessage,
    q.AlertPayload
FROM #LiquidityAlertQueue AS q
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
    h.PositionCode,
    h.ParentPositionCode,
    h.HierarchyLevel,
    h.HierarchyPath
FROM #FundingHierarchy AS h
ORDER BY
    h.PositionCode,
    h.HierarchyLevel;

DROP TABLE IF EXISTS #LiquidityBucketMatrix;
DROP TABLE IF EXISTS #BucketPivotSeed;
DROP TABLE IF EXISTS #FundingHierarchy;
DROP TABLE IF EXISTS #LiquidityAlertQueue;
DROP TABLE IF EXISTS #LiquidityPositionStage;
GO

EXEC dbo.usp_FinalizePortfolioLiquidityWindow
    @WindowCode = N'GLOBAL_PORTFOLIO_LIQUIDITY',
    @ClosedUtc = SYSUTCDATETIME(),
    @ClosedBy = ORIGINAL_LOGIN();
