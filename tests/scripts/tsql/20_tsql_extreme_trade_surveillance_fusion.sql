/* Extreme T-SQL stress sample 8 */
/* Purpose: trade surveillance fusion workflow with recursive account trees, */
/* alert synthesis, settlement horizon pivots, JSON/XML packaging, savepoints, */
/* queue dispatch, and procedural exception recovery. */

SET NOCOUNT ON;
SET XACT_ABORT ON;
SET DEADLOCK_PRIORITY HIGH;

DROP TABLE IF EXISTS #TradeEventStage;
DROP TABLE IF EXISTS #SurveillanceAlertQueue;
DROP TABLE IF EXISTS #AccountHierarchy;
DROP TABLE IF EXISTS #HorizonPivotSeed;

CREATE TABLE #TradeEventStage
(
    StageTradeId BIGINT IDENTITY(1, 1) PRIMARY KEY,
    LoadBatchId UNIQUEIDENTIFIER NOT NULL DEFAULT NEWID(),
    SurveillanceRunCode NVARCHAR(30) NOT NULL,
    DeskCode NVARCHAR(30) NOT NULL,
    ParentAccountCode NVARCHAR(40) NULL,
    AccountCode NVARCHAR(40) NOT NULL,
    OrderCode NVARCHAR(40) NOT NULL,
    TradeCode NVARCHAR(40) NOT NULL,
    InstrumentCode NVARCHAR(40) NOT NULL,
    VenueCode NVARCHAR(20) NOT NULL,
    ProductTypeCode NVARCHAR(20) NOT NULL,
    SettlementHorizonCode NVARCHAR(20) NOT NULL,
    TradeUtc DATETIME2(3) NOT NULL,
    TradeDate DATE NOT NULL,
    SideCode NVARCHAR(10) NOT NULL,
    Quantity NUMERIC(19, 4) NOT NULL,
    Price NUMERIC(19, 6) NOT NULL,
    NotionalAmount NUMERIC(19, 4) NOT NULL,
    MarketReferencePrice NUMERIC(19, 6) NOT NULL,
    SlippageBps NUMERIC(19, 4) NOT NULL,
    ParticipationPct NUMERIC(9, 4) NOT NULL,
    ClientRiskScore INTEGER NULL,
    AlertFloor NUMERIC(19, 4) NOT NULL,
    MarketImpactRatio AS (
        CASE
            WHEN MarketReferencePrice = 0 THEN 0
            ELSE ABS(Price - MarketReferencePrice) / NULLIF(MarketReferencePrice, 0)
        END
    ) PERSISTED,
    EventJson NVARCHAR(MAX) NULL,
    DiagnosticXml XML NULL,
    CreatedUtc DATETIME2(3) NOT NULL DEFAULT SYSUTCDATETIME()
);

CREATE TABLE #SurveillanceAlertQueue
(
    AlertId BIGINT IDENTITY(1, 1) PRIMARY KEY,
    AlertUtc DATETIME2(3) NOT NULL DEFAULT SYSUTCDATETIME(),
    AlertCategory NVARCHAR(40) NOT NULL,
    SeverityCode NVARCHAR(20) NOT NULL,
    SurveillanceRunCode NVARCHAR(30) NULL,
    DeskCode NVARCHAR(30) NULL,
    AccountCode NVARCHAR(40) NULL,
    TradeCode NVARCHAR(40) NULL,
    AlertMessage NVARCHAR(4000) NOT NULL,
    AlertPayload NVARCHAR(MAX) NULL
);

CREATE TABLE #AccountHierarchy
(
    HierarchyRowId BIGINT IDENTITY(1, 1) PRIMARY KEY,
    AccountCode NVARCHAR(40) NOT NULL,
    ParentAccountCode NVARCHAR(40) NULL,
    HierarchyLevel INTEGER NOT NULL,
    HierarchyPath NVARCHAR(4000) NOT NULL
);

CREATE TABLE #HorizonPivotSeed
(
    SurveillanceRunCode NVARCHAR(30) NOT NULL,
    DeskCode NVARCHAR(30) NOT NULL,
    SettlementHorizonCode NVARCHAR(20) NOT NULL,
    FunctionalExposure NUMERIC(19, 4) NOT NULL
);

DECLARE @RunProfile TABLE
(
    SurveillanceRunCode NVARCHAR(30) PRIMARY KEY,
    TargetImpactRatio NUMERIC(19, 4) NOT NULL,
    EscalationBandCode NVARCHAR(20) NOT NULL,
    MaxClientRiskScore INTEGER NOT NULL,
    RunProfileJson NVARCHAR(MAX) NULL
);

DECLARE @AccountEdges TABLE
(
    ParentAccountCode NVARCHAR(40) NOT NULL,
    ChildAccountCode NVARCHAR(40) NOT NULL,
    ExposureLimit NUMERIC(19, 4) NOT NULL,
    EffectiveUtc DATETIME2(3) NOT NULL,
    PRIMARY KEY (ParentAccountCode, ChildAccountCode, EffectiveUtc)
);

DECLARE @InboundTrades TABLE
(
    FeedRowId INTEGER IDENTITY(1, 1) PRIMARY KEY,
    SurveillanceRunCode NVARCHAR(30) NOT NULL,
    DeskCode NVARCHAR(30) NOT NULL,
    ParentAccountCode NVARCHAR(40) NULL,
    AccountCode NVARCHAR(40) NOT NULL,
    OrderCode NVARCHAR(40) NOT NULL,
    TradeCode NVARCHAR(40) NOT NULL,
    InstrumentCode NVARCHAR(40) NOT NULL,
    VenueCode NVARCHAR(20) NOT NULL,
    ProductTypeCode NVARCHAR(20) NOT NULL,
    SettlementHorizonCode NVARCHAR(20) NOT NULL,
    TradeUtc DATETIME2(3) NOT NULL,
    TradeDate DATE NOT NULL,
    SideCode NVARCHAR(10) NOT NULL,
    Quantity NUMERIC(19, 4) NOT NULL,
    Price NUMERIC(19, 6) NOT NULL,
    NotionalAmount NUMERIC(19, 4) NOT NULL,
    MarketReferencePrice NUMERIC(19, 6) NOT NULL,
    SlippageBps NUMERIC(19, 4) NOT NULL,
    ParticipationPct NUMERIC(9, 4) NOT NULL,
    ClientRiskScore INTEGER NULL,
    AlertFloor NUMERIC(19, 4) NOT NULL,
    EventJson NVARCHAR(MAX) NULL,
    DiagnosticXml XML NULL
);

INSERT INTO @RunProfile
(
    SurveillanceRunCode,
    TargetImpactRatio,
    EscalationBandCode,
    MaxClientRiskScore,
    RunProfileJson
)
VALUES
    (N'RUN-EU-OPEN', 0.0120, N'LEVEL1', 72, N'{"owner":"surv-eu","focus":"equities","window":"open"}'),
    (N'RUN-US-CLOSE', 0.0100, N'LEVEL2', 65, N'{"owner":"surv-us","focus":"options","window":"close"}'),
    (N'RUN-APAC-MID', 0.0140, N'LEVEL3', 60, N'{"owner":"surv-apac","focus":"futures","window":"mid"}');

INSERT INTO @AccountEdges
(
    ParentAccountCode,
    ChildAccountCode,
    ExposureLimit,
    EffectiveUtc
)
VALUES
    (N'ACC-ROOT-100', N'ACC-CHILD-101', 125.0000, '2025-01-01T00:00:00'),
    (N'ACC-ROOT-100', N'ACC-CHILD-102', 95.0000, '2025-01-01T00:00:00'),
    (N'ACC-ROOT-500', N'ACC-CHILD-501', 88.0000, '2025-01-01T00:00:00'),
    (N'ACC-ROOT-500', N'ACC-CHILD-502', 66.0000, '2025-01-01T00:00:00');

INSERT INTO @InboundTrades
(
    SurveillanceRunCode,
    DeskCode,
    ParentAccountCode,
    AccountCode,
    OrderCode,
    TradeCode,
    InstrumentCode,
    VenueCode,
    ProductTypeCode,
    SettlementHorizonCode,
    TradeUtc,
    TradeDate,
    SideCode,
    Quantity,
    Price,
    NotionalAmount,
    MarketReferencePrice,
    SlippageBps,
    ParticipationPct,
    ClientRiskScore,
    AlertFloor,
    EventJson,
    DiagnosticXml
)
VALUES
    (
        N'RUN-EU-OPEN',
        N'EQ_ARBITRAGE',
        NULL,
        N'ACC-ROOT-100',
        N'ORD-700001',
        N'TRD-700001',
        N'ISIN-EQ-EU-001',
        N'XPAR',
        N'EQUITY',
        N'T2',
        '2025-12-18T08:15:00',
        '2025-12-18',
        N'BUY',
        18000.0000,
        102.450000,
        1844100.0000,
        101.880000,
        55.0000,
        18.5000,
        78,
        0.0120,
        N'{"priority":"critical","surveillance":{"algoFlag":true,"spoofingScore":88},"settlement":{"manual":false}}',
        '<diag><event code="IMPACT_SPIKE" severity="CRITICAL" /><event code="CLIENT_CLUSTER" severity="HIGH" /></diag>'
    ),
    (
        N'RUN-EU-OPEN',
        N'EQ_ARBITRAGE',
        N'ACC-ROOT-100',
        N'ACC-CHILD-101',
        N'ORD-700002',
        N'TRD-700002',
        N'ISIN-EQ-EU-009',
        N'XPAR',
        N'EQUITY',
        N'T1',
        '2025-12-18T08:15:00',
        '2025-12-18',
        N'SELL',
        6400.0000,
        48.220000,
        308608.0000,
        48.010000,
        19.0000,
        9.2000,
        61,
        0.0100,
        N'{"priority":"high","surveillance":{"algoFlag":false,"spoofingScore":47},"settlement":{"manual":false}}',
        '<diag><event code="ORDER_LAYERING" severity="MEDIUM" /></diag>'
    ),
    (
        N'RUN-US-CLOSE',
        N'OPTIONS_VOL',
        NULL,
        N'ACC-ROOT-500',
        N'ORD-880001',
        N'TRD-880001',
        N'OPT-US-QQQ-CALL',
        N'XNAS',
        N'OPTION',
        N'T0',
        '2025-12-18T21:55:00',
        '2025-12-18',
        N'BUY',
        1200.0000,
        14.880000,
        17856.0000,
        14.120000,
        82.0000,
        22.4000,
        69,
        0.0100,
        N'{"priority":"critical","surveillance":{"algoFlag":true,"spoofingScore":93},"settlement":{"manual":true}}',
        '<diag><event code="CLOSE_AUCTION_PRESSURE" severity="CRITICAL" /></diag>'
    ),
    (
        N'RUN-APAC-MID',
        N'INDEX_FUTURES',
        NULL,
        N'ACC-ROOT-901',
        N'ORD-990001',
        N'TRD-990001',
        N'FUT-JP-IDX-01',
        N'XJPX',
        N'FUTURE',
        N'T1',
        '2025-12-18T03:20:00',
        '2025-12-18',
        N'SELL',
        320.0000,
        2810.500000,
        899360.0000,
        2808.100000,
        8.5000,
        4.2000,
        43,
        0.0140,
        N'{"priority":"medium","surveillance":{"algoFlag":false,"spoofingScore":18},"settlement":{"manual":false}}',
        '<diag><event code="NORMAL" severity="INFO" /></diag>'
    );

INSERT INTO #TradeEventStage
(
    SurveillanceRunCode,
    DeskCode,
    ParentAccountCode,
    AccountCode,
    OrderCode,
    TradeCode,
    InstrumentCode,
    VenueCode,
    ProductTypeCode,
    SettlementHorizonCode,
    TradeUtc,
    TradeDate,
    SideCode,
    Quantity,
    Price,
    NotionalAmount,
    MarketReferencePrice,
    SlippageBps,
    ParticipationPct,
    ClientRiskScore,
    AlertFloor,
    EventJson,
    DiagnosticXml
)
SELECT
    t.SurveillanceRunCode,
    t.DeskCode,
    t.ParentAccountCode,
    t.AccountCode,
    t.OrderCode,
    t.TradeCode,
    t.InstrumentCode,
    t.VenueCode,
    t.ProductTypeCode,
    t.SettlementHorizonCode,
    t.TradeUtc,
    t.TradeDate,
    t.SideCode,
    t.Quantity,
    t.Price,
    t.NotionalAmount,
    t.MarketReferencePrice,
    t.SlippageBps,
    t.ParticipationPct,
    t.ClientRiskScore,
    t.AlertFloor,
    t.EventJson,
    t.DiagnosticXml
FROM @InboundTrades AS t;

BEGIN TRY
    BEGIN TRANSACTION;
    SAVE TRANSACTION BeforeSurveillanceEvaluation;

    WITH AccountTree AS
    (
        SELECT
            t.AccountCode,
            t.ParentAccountCode,
            0 AS HierarchyLevel,
            CAST(CONCAT(t.AccountCode, N'>') AS NVARCHAR(4000)) AS HierarchyPath
        FROM #TradeEventStage AS t
        WHERE t.ParentAccountCode IS NULL

        UNION ALL

        SELECT
            c.AccountCode,
            c.ParentAccountCode,
            at.HierarchyLevel + 1,
            CAST(at.HierarchyPath + c.AccountCode + N'>' AS NVARCHAR(4000))
        FROM #TradeEventStage AS c
        INNER JOIN AccountTree AS at
            ON c.ParentAccountCode = at.AccountCode
    )
    INSERT INTO #AccountHierarchy
    (
        AccountCode,
        ParentAccountCode,
        HierarchyLevel,
        HierarchyPath
    )
    SELECT
        at.AccountCode,
        at.ParentAccountCode,
        at.HierarchyLevel,
        at.HierarchyPath
    FROM AccountTree AS at
    OPTION (MAXRECURSION 100);

    WITH TradeEnrichment AS
    (
        SELECT
            t.StageTradeId,
            t.SurveillanceRunCode,
            t.DeskCode,
            t.AccountCode,
            t.OrderCode,
            t.TradeCode,
            t.InstrumentCode,
            t.VenueCode,
            t.ProductTypeCode,
            t.SettlementHorizonCode,
            t.TradeUtc,
            t.Quantity,
            t.Price,
            t.NotionalAmount,
            t.MarketReferencePrice,
            t.SlippageBps,
            t.ParticipationPct,
            t.ClientRiskScore,
            t.AlertFloor,
            t.MarketImpactRatio,
            rp.TargetImpactRatio,
            rp.EscalationBandCode,
            rp.MaxClientRiskScore,
            ISNULL(JSON_QUERY(t.EventJson, '$.priority'), JSON_VALUE(t.EventJson, '$.priority')) AS PriorityCode,
            TRY_CAST(ISNULL(JSON_QUERY(t.EventJson, '$.surveillance.algoFlag'), JSON_VALUE(t.EventJson, '$.surveillance.algoFlag')) AS BIT) AS IsAlgoOrder,
            TRY_CAST(ISNULL(JSON_QUERY(t.EventJson, '$.surveillance.spoofingScore'), JSON_VALUE(t.EventJson, '$.surveillance.spoofingScore')) AS INTEGER) AS SpoofingScore,
            TRY_CAST(ISNULL(JSON_QUERY(t.EventJson, '$.settlement.manual'), JSON_VALUE(t.EventJson, '$.settlement.manual')) AS BIT) AS IsManualSettlement,
            ah.HierarchyLevel,
            ah.HierarchyPath,
            DENSE_RANK() OVER (PARTITION BY t.SurveillanceRunCode, t.DeskCode ORDER BY t.MarketImpactRatio DESC, t.TradeUtc DESC) AS ImpactRank,
            SUM(t.NotionalAmount) OVER (PARTITION BY t.SurveillanceRunCode, t.DeskCode, t.SettlementHorizonCode) AS TotalNotionalByHorizon
        FROM #TradeEventStage AS t
        INNER JOIN @RunProfile AS rp
            ON rp.SurveillanceRunCode = t.SurveillanceRunCode
        LEFT JOIN #AccountHierarchy AS ah
            ON ah.AccountCode = t.AccountCode
    ),
    AccountExpansion AS
    (
        SELECT
            te.AccountCode AS RootAccountCode,
            te.AccountCode AS CurrentAccountCode,
            CAST(0.0000 AS NUMERIC(19, 4)) AS ExposureLimitUsed,
            0 AS AccountLevel,
            CAST(te.AccountCode + N'>' AS NVARCHAR(4000)) AS AccountPath
        FROM TradeEnrichment AS te

        UNION ALL

        SELECT
            ae.RootAccountCode,
            e.ChildAccountCode,
            CAST(ae.ExposureLimitUsed + e.ExposureLimit AS NUMERIC(19, 4)),
            ae.AccountLevel + 1,
            CAST(ae.AccountPath + e.ChildAccountCode + N'>' AS NVARCHAR(4000))
        FROM AccountExpansion AS ae
        INNER JOIN @AccountEdges AS e
            ON e.ParentAccountCode = ae.CurrentAccountCode
        WHERE ae.AccountLevel < 5
    ),
    SurveillanceSignals AS
    (
        SELECT
            te.StageTradeId,
            te.SurveillanceRunCode,
            te.DeskCode,
            te.AccountCode,
            te.TradeCode,
            te.PriorityCode,
            te.EscalationBandCode,
            te.TargetImpactRatio,
            te.MaxClientRiskScore,
            te.IsAlgoOrder,
            te.SpoofingScore,
            te.IsManualSettlement,
            te.MarketImpactRatio,
            te.ClientRiskScore,
            te.TotalNotionalByHorizon,
            te.ImpactRank,
            COUNT(*) AS ReachableAccounts,
            MAX(ae.AccountLevel) AS MaxAccountDepth,
            CASE
                WHEN te.MarketImpactRatio > te.TargetImpactRatio AND te.PriorityCode = N'critical' THEN N'CRITICAL_IMPACT_BREACH'
                WHEN te.ClientRiskScore > te.MaxClientRiskScore AND te.IsManualSettlement = 1 THEN N'MANUAL_SETTLEMENT_SURGE'
                WHEN te.SpoofingScore >= 80 AND te.IsAlgoOrder = 1 THEN N'ALGO_SPOOFING_RISK'
                WHEN te.TotalNotionalByHorizon > 2000000.0000 AND te.ImpactRank = 1 THEN N'HORIZON_CONCENTRATION_BREACH'
                ELSE N'NORMAL'
            END AS SignalCode
        FROM TradeEnrichment AS te
        LEFT JOIN AccountExpansion AS ae
            ON ae.RootAccountCode = te.AccountCode
        GROUP BY
            te.StageTradeId,
            te.SurveillanceRunCode,
            te.DeskCode,
            te.AccountCode,
            te.TradeCode,
            te.PriorityCode,
            te.EscalationBandCode,
            te.TargetImpactRatio,
            te.MaxClientRiskScore,
            te.IsAlgoOrder,
            te.SpoofingScore,
            te.IsManualSettlement,
            te.MarketImpactRatio,
            te.ClientRiskScore,
            te.TotalNotionalByHorizon,
            te.ImpactRank
    )
    INSERT INTO #SurveillanceAlertQueue
    (
        AlertCategory,
        SeverityCode,
        SurveillanceRunCode,
        DeskCode,
        AccountCode,
        TradeCode,
        AlertMessage,
        AlertPayload
    )
    SELECT
        N'SURVEILLANCE_SIGNAL',
        CASE
            WHEN s.SignalCode IN (N'CRITICAL_IMPACT_BREACH', N'MANUAL_SETTLEMENT_SURGE') THEN N'CRITICAL'
            WHEN s.SignalCode IN (N'ALGO_SPOOFING_RISK', N'HORIZON_CONCENTRATION_BREACH') THEN N'HIGH'
            ELSE N'MEDIUM'
        END,
        s.SurveillanceRunCode,
        s.DeskCode,
        s.AccountCode,
        s.TradeCode,
        CONCAT(N'Surveillance signal detected for trade ', s.TradeCode, N': ', s.SignalCode),
        (
            SELECT
                s.PriorityCode AS [priority],
                s.EscalationBandCode AS [escalationBand],
                s.MarketImpactRatio AS [marketImpactRatio],
                s.ClientRiskScore AS [clientRiskScore],
                s.SpoofingScore AS [spoofingScore],
                s.TotalNotionalByHorizon AS [totalNotionalByHorizon],
                s.ReachableAccounts AS [reachableAccounts],
                s.MaxAccountDepth AS [maxAccountDepth]
            FOR JSON PATH, ROOT('surveillanceAlert'), INCLUDE_NULL_VALUES
        )
    FROM SurveillanceSignals AS s
    WHERE s.SignalCode <> N'NORMAL';

    INSERT INTO #HorizonPivotSeed
    (
        SurveillanceRunCode,
        DeskCode,
        SettlementHorizonCode,
        FunctionalExposure
    )
    SELECT
        t.SurveillanceRunCode,
        t.DeskCode,
        t.SettlementHorizonCode,
        t.NotionalAmount * CASE WHEN t.SideCode = N'BUY' THEN 1 ELSE -1 END
    FROM #TradeEventStage AS t;

    DECLARE @PivotColumns NVARCHAR(MAX);
    DECLARE @PivotSql NVARCHAR(MAX);

    SELECT
        @PivotColumns = STRING_AGG(QUOTENAME(SettlementHorizonCode), N',')
    FROM
    (
        SELECT DISTINCT SettlementHorizonCode
        FROM #HorizonPivotSeed
    ) AS settlement_horizons;

    SET @PivotSql = N'
        SELECT SurveillanceRunCode, DeskCode, ' + @PivotColumns + N'
        INTO #SurveillanceHorizonMatrix
        FROM
        (
            SELECT SurveillanceRunCode, DeskCode, SettlementHorizonCode, FunctionalExposure
            FROM #HorizonPivotSeed
        ) src
        PIVOT
        (
            SUM(FunctionalExposure)
            FOR SettlementHorizonCode IN (' + @PivotColumns + N')
        ) p;';

    EXEC sys.sp_executesql @PivotSql;

    MERGE INTO dbo.TradeSurveillanceSnapshot AS target
    USING
    (
        SELECT
            t.SurveillanceRunCode,
            t.DeskCode,
            COUNT(*) AS TradeCount,
            SUM(t.NotionalAmount) AS TotalNotionalAmount,
            AVG(t.MarketImpactRatio) AS AvgMarketImpactRatio,
            MAX(t.TradeUtc) AS LastTradeUtc,
            SYSUTCDATETIME() AS RefreshUtc
        FROM #TradeEventStage AS t
        GROUP BY
            t.SurveillanceRunCode,
            t.DeskCode
    ) AS source
        ON target.SurveillanceRunCode = source.SurveillanceRunCode
       AND target.DeskCode = source.DeskCode
    WHEN MATCHED THEN
        UPDATE SET
            target.TradeCount = source.TradeCount,
            target.TotalNotionalAmount = source.TotalNotionalAmount,
            target.AvgMarketImpactRatio = source.AvgMarketImpactRatio,
            target.LastTradeUtc = source.LastTradeUtc,
            target.LastRefreshUtc = source.RefreshUtc
    WHEN NOT MATCHED THEN
        INSERT
        (
            SurveillanceRunCode,
            DeskCode,
            TradeCount,
            TotalNotionalAmount,
            AvgMarketImpactRatio,
            LastTradeUtc,
            LastRefreshUtc
        )
        VALUES
        (
            source.SurveillanceRunCode,
            source.DeskCode,
            source.TradeCount,
            source.TotalNotionalAmount,
            source.AvgMarketImpactRatio,
            source.LastTradeUtc,
            source.RefreshUtc
        )
    OUTPUT
        $action,
        inserted.SurveillanceRunCode,
        inserted.DeskCode,
        inserted.LastRefreshUtc
    INTO dbo.TradeSurveillanceAudit
    (
        MergeAction,
        SurveillanceRunCode,
        DeskCode,
        AuditUtc
    );

    IF EXISTS
    (
        SELECT 1
        FROM #SurveillanceAlertQueue
        WHERE SeverityCode = N'CRITICAL'
    )
    BEGIN
        WAITFOR DELAY '00:00:01';
    END;

    DECLARE @DispatchRunCode AS NVARCHAR(30);
    DECLARE @DispatchDeskCode AS NVARCHAR(30);
    DECLARE @DispatchTradeCode AS NVARCHAR(40);

    DECLARE SurveillanceDispatchCursor CURSOR LOCAL FAST_FORWARD FOR
        SELECT
            q.SurveillanceRunCode,
            q.DeskCode,
            q.TradeCode
        FROM #SurveillanceAlertQueue AS q
        WHERE q.SeverityCode IN (N'CRITICAL', N'HIGH')
        ORDER BY q.AlertUtc, q.AlertId;

    OPEN SurveillanceDispatchCursor;
    FETCH NEXT FROM SurveillanceDispatchCursor
        INTO @DispatchRunCode, @DispatchDeskCode, @DispatchTradeCode;

    WHILE @@FETCH_STATUS = 0
    BEGIN
        EXEC dbo.usp_DispatchSurveillanceEscalation
            @SurveillanceRunCode = @DispatchRunCode,
            @DeskCode = @DispatchDeskCode,
            @TradeCode = @DispatchTradeCode,
            @RequestedUtc = SYSUTCDATETIME();

        FETCH NEXT FROM SurveillanceDispatchCursor
            INTO @DispatchRunCode, @DispatchDeskCode, @DispatchTradeCode;
    END;

    CLOSE SurveillanceDispatchCursor;
    DEALLOCATE SurveillanceDispatchCursor;

    INSERT INTO dbo.TradeSurveillanceRuns
    (
        RunUtc,
        RunCategory,
        FinalStateCode,
        AlertEnvelopeJson,
        AccountEnvelopeXml
    )
    SELECT
        SYSUTCDATETIME(),
        N'TRADE_SURVEILLANCE',
        CASE
            WHEN EXISTS (SELECT 1 FROM #SurveillanceAlertQueue WHERE SeverityCode = N'CRITICAL') THEN N'ESCALATED'
            WHEN EXISTS (SELECT 1 FROM #SurveillanceAlertQueue) THEN N'WARNINGS'
            ELSE N'CLEAR'
        END,
        (
            SELECT
                q.AlertCategory,
                q.SeverityCode,
                q.SurveillanceRunCode,
                q.DeskCode,
                q.AccountCode,
                q.TradeCode,
                q.AlertMessage
            FROM #SurveillanceAlertQueue AS q
            FOR JSON PATH, ROOT('alerts'), INCLUDE_NULL_VALUES
        ),
        (
            SELECT
                h.AccountCode AS [@accountCode],
                h.ParentAccountCode AS [@parentAccountCode],
                h.HierarchyLevel AS [@level],
                h.HierarchyPath AS [path]
            FROM #AccountHierarchy AS h
            FOR XML PATH('account'), ROOT('accounts'), TYPE
        );

    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    IF CURSOR_STATUS('local', 'SurveillanceDispatchCursor') >= -1
    BEGIN
        CLOSE SurveillanceDispatchCursor;
        DEALLOCATE SurveillanceDispatchCursor;
    END;

    IF XACT_STATE() = -1
        ROLLBACK TRANSACTION;
    ELSE IF XACT_STATE() = 1
        ROLLBACK TRANSACTION BeforeSurveillanceEvaluation;

    INSERT INTO #SurveillanceAlertQueue
    (
        AlertCategory,
        SeverityCode,
        SurveillanceRunCode,
        DeskCode,
        AccountCode,
        TradeCode,
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
    q.SurveillanceRunCode,
    q.DeskCode,
    q.AccountCode,
    q.TradeCode,
    q.AlertMessage,
    q.AlertPayload
FROM #SurveillanceAlertQueue AS q
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
    h.AccountCode,
    h.ParentAccountCode,
    h.HierarchyLevel,
    h.HierarchyPath
FROM #AccountHierarchy AS h
ORDER BY
    h.AccountCode,
    h.HierarchyLevel;

DROP TABLE IF EXISTS #SurveillanceHorizonMatrix;
DROP TABLE IF EXISTS #HorizonPivotSeed;
DROP TABLE IF EXISTS #AccountHierarchy;
DROP TABLE IF EXISTS #SurveillanceAlertQueue;
DROP TABLE IF EXISTS #TradeEventStage;
GO

EXEC dbo.usp_FinalizeTradeSurveillanceWindow
    @WindowCode = N'GLOBAL_TRADE_SURVEILLANCE',
    @ClosedUtc = SYSUTCDATETIME(),
    @ClosedBy = ORIGINAL_LOGIN();
