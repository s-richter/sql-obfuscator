/* Extreme T-SQL stress sample 4 */
/* Purpose: manufacturing control tower workflow with recursive BOM traversal, */
/* event normalization, quality escalation, dynamic capacity pivots, */
/* savepoints, cursor-driven dispatch, and mixed JSON/XML packaging. */

SET NOCOUNT ON;
SET XACT_ABORT ON;
SET DEADLOCK_PRIORITY HIGH;

DROP TABLE IF EXISTS #ProductionEventStage;
DROP TABLE IF EXISTS #QualityAlertQueue;
DROP TABLE IF EXISTS #LineageGraph;
DROP TABLE IF EXISTS #CapacityPivotSeed;

CREATE TABLE #ProductionEventStage
(
    StageEventId BIGINT IDENTITY(1, 1) PRIMARY KEY,
    EventBatchId UNIQUEIDENTIFIER NOT NULL DEFAULT NEWID(),
    PlantCode NVARCHAR(20) NOT NULL,
    WorkCenterCode NVARCHAR(30) NOT NULL,
    ProductionLineCode NVARCHAR(30) NOT NULL,
    ParentLotNumber NVARCHAR(40) NULL,
    LotNumber NVARCHAR(40) NOT NULL,
    MaterialCode NVARCHAR(40) NOT NULL,
    BomNodeCode NVARCHAR(40) NOT NULL,
    RoutingCode NVARCHAR(30) NOT NULL,
    ShiftCode NVARCHAR(10) NOT NULL,
    EventTypeCode NVARCHAR(30) NOT NULL,
    EventStatusCode NVARCHAR(30) NOT NULL,
    EventUtc DATETIME2(3) NOT NULL,
    PlannedStartUtc DATETIME2(3) NULL,
    PlannedEndUtc DATETIME2(3) NULL,
    ActualStartUtc DATETIME2(3) NULL,
    ActualEndUtc DATETIME2(3) NULL,
    UnitsPlanned NUMERIC(19, 4) NOT NULL,
    UnitsCompleted NUMERIC(19, 4) NOT NULL,
    UnitsScrapped NUMERIC(19, 4) NOT NULL,
    UnitsReworked NUMERIC(19, 4) NOT NULL,
    LaborHours NUMERIC(19, 4) NOT NULL,
    MachineHours NUMERIC(19, 4) NOT NULL,
    EnergyKwh NUMERIC(19, 4) NOT NULL,
    TemperatureC NUMERIC(9, 3) NULL,
    VibrationMmS NUMERIC(9, 3) NULL,
    OeePercent AS
    (
        CASE
            WHEN UnitsPlanned = 0 THEN 0
            ELSE ((UnitsCompleted - UnitsScrapped) / NULLIF(UnitsPlanned, 0)) * 100.0000
        END
    ) PERSISTED,
    EventJson NVARCHAR(MAX) NULL,
    DiagnosticXml XML NULL,
    CreatedUtc DATETIME2(3) NOT NULL DEFAULT SYSUTCDATETIME()
);

CREATE TABLE #QualityAlertQueue
(
    AlertId BIGINT IDENTITY(1, 1) PRIMARY KEY,
    AlertUtc DATETIME2(3) NOT NULL DEFAULT SYSUTCDATETIME(),
    AlertCategory NVARCHAR(40) NOT NULL,
    SeverityCode NVARCHAR(20) NOT NULL,
    PlantCode NVARCHAR(20) NULL,
    WorkCenterCode NVARCHAR(30) NULL,
    LotNumber NVARCHAR(40) NULL,
    MaterialCode NVARCHAR(40) NULL,
    AlertMessage NVARCHAR(4000) NOT NULL,
    AlertPayload NVARCHAR(MAX) NULL
);

CREATE TABLE #LineageGraph
(
    GraphRowId BIGINT IDENTITY(1, 1) PRIMARY KEY,
    LotNumber NVARCHAR(40) NOT NULL,
    ParentLotNumber NVARCHAR(40) NULL,
    HierarchyLevel INTEGER NOT NULL,
    TraversalPath NVARCHAR(4000) NOT NULL
);

CREATE TABLE #CapacityPivotSeed
(
    PlantCode NVARCHAR(20) NOT NULL,
    WorkCenterCode NVARCHAR(30) NOT NULL,
    ShiftCode NVARCHAR(10) NOT NULL,
    FunctionalHours NUMERIC(19, 4) NOT NULL
);

DECLARE @PlantMaster TABLE
(
    PlantCode NVARCHAR(20) PRIMARY KEY,
    RegionCode NVARCHAR(20) NOT NULL,
    EscalationTier NVARCHAR(10) NOT NULL,
    UtilityRiskScore INTEGER NOT NULL,
    PlantProfileJson NVARCHAR(MAX) NULL
);

DECLARE @BomEdges TABLE
(
    ParentBomNodeCode NVARCHAR(40) NOT NULL,
    ChildBomNodeCode NVARCHAR(40) NOT NULL,
    QuantityPer NUMERIC(19, 6) NOT NULL,
    EffectiveUtc DATETIME2(3) NOT NULL,
    PRIMARY KEY (ParentBomNodeCode, ChildBomNodeCode, EffectiveUtc)
);

DECLARE @InboundEvents TABLE
(
    FeedRowId INTEGER IDENTITY(1, 1) PRIMARY KEY,
    PlantCode NVARCHAR(20) NOT NULL,
    WorkCenterCode NVARCHAR(30) NOT NULL,
    ProductionLineCode NVARCHAR(30) NOT NULL,
    ParentLotNumber NVARCHAR(40) NULL,
    LotNumber NVARCHAR(40) NOT NULL,
    MaterialCode NVARCHAR(40) NOT NULL,
    BomNodeCode NVARCHAR(40) NOT NULL,
    RoutingCode NVARCHAR(30) NOT NULL,
    ShiftCode NVARCHAR(10) NOT NULL,
    EventTypeCode NVARCHAR(30) NOT NULL,
    EventStatusCode NVARCHAR(30) NOT NULL,
    EventUtc DATETIME2(3) NOT NULL,
    PlannedStartUtc DATETIME2(3) NULL,
    PlannedEndUtc DATETIME2(3) NULL,
    ActualStartUtc DATETIME2(3) NULL,
    ActualEndUtc DATETIME2(3) NULL,
    UnitsPlanned NUMERIC(19, 4) NOT NULL,
    UnitsCompleted NUMERIC(19, 4) NOT NULL,
    UnitsScrapped NUMERIC(19, 4) NOT NULL,
    UnitsReworked NUMERIC(19, 4) NOT NULL,
    LaborHours NUMERIC(19, 4) NOT NULL,
    MachineHours NUMERIC(19, 4) NOT NULL,
    EnergyKwh NUMERIC(19, 4) NOT NULL,
    TemperatureC NUMERIC(9, 3) NULL,
    VibrationMmS NUMERIC(9, 3) NULL,
    EventJson NVARCHAR(MAX) NULL,
    DiagnosticXml XML NULL
);

INSERT INTO @PlantMaster
(
    PlantCode,
    RegionCode,
    EscalationTier,
    UtilityRiskScore,
    PlantProfileJson
)
VALUES
    (N'PLT-SE-01', N'NORDICS', N'T1', 38, N'{"owner":"grid-a","backupGen":true,"focus":"medical-devices"}'),
    (N'PLT-DE-04', N'EUROPE', N'T2', 21, N'{"owner":"grid-b","backupGen":true,"focus":"industrial-controls"}'),
    (N'PLT-US-09', N'AMERICAS', N'T1', 44, N'{"owner":"grid-c","backupGen":false,"focus":"semiconductor-packaging"}'),
    (N'PLT-MX-02', N'AMERICAS', N'T3', 57, N'{"owner":"grid-d","backupGen":false,"focus":"wire-harness"}');

INSERT INTO @BomEdges
(
    ParentBomNodeCode,
    ChildBomNodeCode,
    QuantityPer,
    EffectiveUtc
)
VALUES
    (N'BOM-FIN-100', N'BOM-SUB-110', 1.000000, '2025-01-01T00:00:00'),
    (N'BOM-FIN-100', N'BOM-SUB-120', 2.000000, '2025-01-01T00:00:00'),
    (N'BOM-SUB-110', N'BOM-CMP-211', 4.000000, '2025-01-01T00:00:00'),
    (N'BOM-SUB-110', N'BOM-CMP-212', 6.000000, '2025-01-01T00:00:00'),
    (N'BOM-SUB-120', N'BOM-CMP-310', 8.000000, '2025-01-01T00:00:00'),
    (N'BOM-SUB-120', N'BOM-CMP-311', 3.000000, '2025-01-01T00:00:00');

INSERT INTO @InboundEvents
(
    PlantCode,
    WorkCenterCode,
    ProductionLineCode,
    ParentLotNumber,
    LotNumber,
    MaterialCode,
    BomNodeCode,
    RoutingCode,
    ShiftCode,
    EventTypeCode,
    EventStatusCode,
    EventUtc,
    PlannedStartUtc,
    PlannedEndUtc,
    ActualStartUtc,
    ActualEndUtc,
    UnitsPlanned,
    UnitsCompleted,
    UnitsScrapped,
    UnitsReworked,
    LaborHours,
    MachineHours,
    EnergyKwh,
    TemperatureC,
    VibrationMmS,
    EventJson,
    DiagnosticXml
)
VALUES
    (
        N'PLT-SE-01',
        N'WC-MIX-01',
        N'LINE-A1',
        NULL,
        N'LOT-900001',
        N'MAT-CTRL-900',
        N'BOM-FIN-100',
        N'ROUTE-FINAL-01',
        N'DAY',
        N'RUN',
        N'ACTIVE',
        '2025-12-11T06:15:00',
        '2025-12-11T06:00:00',
        '2025-12-11T10:00:00',
        '2025-12-11T06:07:00',
        NULL,
        1200.0000,
        910.0000,
        24.0000,
        8.0000,
        18.5000,
        11.2500,
        843.5000,
        6.200,
        1.420,
        N'{"priority":"critical","recipe":"RCP-71","quality":{"hold":false,"limitPpm":1500},"maintenance":{"overdue":true}}',
        '<diag><alarm code="TEMP_DRIFT" severity="HIGH" /><alarm code="MOTOR_LOAD" severity="MEDIUM" /></diag>'
    ),
    (
        N'PLT-SE-01',
        N'WC-ASM-02',
        N'LINE-A2',
        N'LOT-900001',
        N'LOT-900001-01',
        N'MAT-SUB-110',
        N'BOM-SUB-110',
        N'ROUTE-SUB-11',
        N'DAY',
        N'RUN',
        N'ACTIVE',
        '2025-12-11T07:05:00',
        '2025-12-11T07:00:00',
        '2025-12-11T09:30:00',
        '2025-12-11T07:03:00',
        NULL,
        2400.0000,
        2030.0000,
        61.0000,
        12.0000,
        10.2500,
        8.7500,
        413.0000,
        7.100,
        2.880,
        N'{"priority":"high","recipe":"RCP-44","quality":{"hold":true,"limitPpm":900},"maintenance":{"overdue":false}}',
        '<diag><alarm code="VISION_REJECT" severity="HIGH" /></diag>'
    ),
    (
        N'PLT-DE-04',
        N'WC-TEST-08',
        N'LINE-T8',
        NULL,
        N'LOT-770010',
        N'MAT-BOARD-210',
        N'BOM-CMP-211',
        N'ROUTE-TEST-09',
        N'NIGHT',
        N'RUN',
        N'COMPLETE',
        '2025-12-10T21:40:00',
        '2025-12-10T20:30:00',
        '2025-12-10T23:00:00',
        '2025-12-10T20:25:00',
        '2025-12-10T22:54:00',
        5000.0000,
        4980.0000,
        6.0000,
        0.0000,
        14.0000,
        7.0000,
        291.4000,
        4.800,
        0.940,
        N'{"priority":"standard","recipe":"RCP-19","quality":{"hold":false,"limitPpm":600},"maintenance":{"overdue":false}}',
        '<diag><alarm code="NONE" severity="INFO" /></diag>'
    ),
    (
        N'PLT-US-09',
        N'WC-PACK-03',
        N'LINE-P3',
        NULL,
        N'LOT-660031',
        N'MAT-PKG-330',
        N'BOM-CMP-310',
        N'ROUTE-PACK-03',
        N'SWING',
        N'STOP',
        N'HOLD',
        '2025-12-11T13:20:00',
        '2025-12-11T12:00:00',
        '2025-12-11T15:00:00',
        '2025-12-11T12:05:00',
        NULL,
        8200.0000,
        3010.0000,
        144.0000,
        37.0000,
        22.0000,
        17.5000,
        1208.6000,
        9.900,
        4.650,
        N'{"priority":"critical","recipe":"RCP-88","quality":{"hold":true,"limitPpm":500},"maintenance":{"overdue":true}}',
        '<diag><alarm code="SEAL_PRESSURE" severity="CRITICAL" /><alarm code="VACUUM_DROP" severity="HIGH" /></diag>'
    );

INSERT INTO #ProductionEventStage
(
    PlantCode,
    WorkCenterCode,
    ProductionLineCode,
    ParentLotNumber,
    LotNumber,
    MaterialCode,
    BomNodeCode,
    RoutingCode,
    ShiftCode,
    EventTypeCode,
    EventStatusCode,
    EventUtc,
    PlannedStartUtc,
    PlannedEndUtc,
    ActualStartUtc,
    ActualEndUtc,
    UnitsPlanned,
    UnitsCompleted,
    UnitsScrapped,
    UnitsReworked,
    LaborHours,
    MachineHours,
    EnergyKwh,
    TemperatureC,
    VibrationMmS,
    EventJson,
    DiagnosticXml
)
SELECT
    e.PlantCode,
    e.WorkCenterCode,
    e.ProductionLineCode,
    e.ParentLotNumber,
    e.LotNumber,
    e.MaterialCode,
    e.BomNodeCode,
    e.RoutingCode,
    e.ShiftCode,
    e.EventTypeCode,
    e.EventStatusCode,
    e.EventUtc,
    e.PlannedStartUtc,
    e.PlannedEndUtc,
    e.ActualStartUtc,
    e.ActualEndUtc,
    e.UnitsPlanned,
    e.UnitsCompleted,
    e.UnitsScrapped,
    e.UnitsReworked,
    e.LaborHours,
    e.MachineHours,
    e.EnergyKwh,
    e.TemperatureC,
    e.VibrationMmS,
    e.EventJson,
    e.DiagnosticXml
FROM @InboundEvents AS e;

BEGIN TRY
    BEGIN TRANSACTION;
    SAVE TRANSACTION BeforeControlTowerEvaluation;

    WITH LotGraph AS
    (
        SELECT
            s.LotNumber,
            s.ParentLotNumber,
            0 AS HierarchyLevel,
            CAST(CONCAT(s.LotNumber, N'>') AS NVARCHAR(4000)) AS TraversalPath
        FROM #ProductionEventStage AS s
        WHERE s.ParentLotNumber IS NULL

        UNION ALL

        SELECT
            c.LotNumber,
            c.ParentLotNumber,
            g.HierarchyLevel + 1,
            CAST(g.TraversalPath + c.LotNumber + N'>' AS NVARCHAR(4000))
        FROM #ProductionEventStage AS c
        INNER JOIN LotGraph AS g
            ON c.ParentLotNumber = g.LotNumber
    )
    INSERT INTO #LineageGraph
    (
        LotNumber,
        ParentLotNumber,
        HierarchyLevel,
        TraversalPath
    )
    SELECT
        g.LotNumber,
        g.ParentLotNumber,
        g.HierarchyLevel,
        g.TraversalPath
    FROM LotGraph AS g
    OPTION (MAXRECURSION 100);

    WITH EventEnrichment AS
    (
        SELECT
            s.StageEventId,
            s.PlantCode,
            s.WorkCenterCode,
            s.ProductionLineCode,
            s.LotNumber,
            s.MaterialCode,
            s.BomNodeCode,
            s.EventTypeCode,
            s.EventStatusCode,
            s.EventUtc,
            s.UnitsPlanned,
            s.UnitsCompleted,
            s.UnitsScrapped,
            s.UnitsReworked,
            s.LaborHours,
            s.MachineHours,
            s.EnergyKwh,
            s.TemperatureC,
            s.VibrationMmS,
            s.OeePercent,
            pm.RegionCode,
            pm.EscalationTier,
            pm.UtilityRiskScore,
            ISNULL(JSON_QUERY(s.EventJson, '$.priority'), JSON_VALUE(s.EventJson, '$.priority')) AS EventPriority,
            TRY_CAST(ISNULL(JSON_QUERY(s.EventJson, '$.quality.limitPpm'), JSON_VALUE(s.EventJson, '$.quality.limitPpm')) AS INTEGER) AS LimitPpm,
            TRY_CAST(ISNULL(JSON_QUERY(s.EventJson, '$.quality.hold'), JSON_VALUE(s.EventJson, '$.quality.hold')) AS BIT) AS IsQualityHold,
            TRY_CAST(ISNULL(JSON_QUERY(s.EventJson, '$.maintenance.overdue'), JSON_VALUE(s.EventJson, '$.maintenance.overdue')) AS BIT) AS IsMaintenanceOverdue,
            lg.HierarchyLevel,
            lg.TraversalPath,
            DATEDIFF(MINUTE, s.PlannedEndUtc, SYSUTCDATETIME()) AS MinutesPastPlannedEnd,
            DENSE_RANK() OVER (PARTITION BY s.PlantCode, s.WorkCenterCode ORDER BY s.UnitsScrapped DESC, s.EventUtc DESC) AS ScrapRankByCenter,
            SUM(s.UnitsScrapped) OVER (PARTITION BY s.PlantCode, s.WorkCenterCode) AS TotalScrapByCenter
        FROM #ProductionEventStage AS s
        INNER JOIN @PlantMaster AS pm
            ON pm.PlantCode = s.PlantCode
        LEFT JOIN #LineageGraph AS lg
            ON lg.LotNumber = s.LotNumber
    ),
    BomExplosion AS
    (
        SELECT
            e.BomNodeCode AS RootBomNodeCode,
            e.BomNodeCode AS CurrentBomNodeCode,
            CAST(1.000000 AS NUMERIC(19, 6)) AS EffectiveQty,
            0 AS ExplosionLevel,
            CAST(e.BomNodeCode + N'>' AS NVARCHAR(4000)) AS ExplosionPath
        FROM EventEnrichment AS e

        UNION ALL

        SELECT
            bx.RootBomNodeCode,
            be.ChildBomNodeCode,
            CAST(bx.EffectiveQty * be.QuantityPer AS NUMERIC(19, 6)),
            bx.ExplosionLevel + 1,
            CAST(bx.ExplosionPath + be.ChildBomNodeCode + N'>' AS NVARCHAR(4000))
        FROM BomExplosion AS bx
        INNER JOIN @BomEdges AS be
            ON be.ParentBomNodeCode = bx.CurrentBomNodeCode
        WHERE bx.ExplosionLevel < 6
    ),
    RiskSignals AS
    (
        SELECT
            e.StageEventId,
            e.PlantCode,
            e.WorkCenterCode,
            e.LotNumber,
            e.MaterialCode,
            e.EventPriority,
            e.RegionCode,
            e.EscalationTier,
            e.UtilityRiskScore,
            e.LimitPpm,
            e.IsQualityHold,
            e.IsMaintenanceOverdue,
            e.MinutesPastPlannedEnd,
            e.ScrapRankByCenter,
            e.TotalScrapByCenter,
            e.OeePercent,
            e.TemperatureC,
            e.VibrationMmS,
            COUNT(*) AS BomReachCount,
            MAX(bx.ExplosionLevel) AS MaxBomDepth,
            CASE
                WHEN e.IsQualityHold = 1 AND e.EventPriority = N'critical' THEN N'CRITICAL_QUALITY_HOLD'
                WHEN e.IsMaintenanceOverdue = 1 AND COALESCE(e.VibrationMmS, 0) >= 4.000 THEN N'PREDICTIVE_MAINTENANCE_BREACH'
                WHEN e.MinutesPastPlannedEnd > 120 AND e.EventStatusCode <> N'COMPLETE' THEN N'EXTENDED_RUNTIME_BREACH'
                WHEN e.OeePercent < 85.0000 AND e.TotalScrapByCenter > 100 THEN N'CENTER_YIELD_DEGRADATION'
                ELSE N'NORMAL'
            END AS RiskStateCode
        FROM EventEnrichment AS e
        LEFT JOIN BomExplosion AS bx
            ON bx.RootBomNodeCode = e.BomNodeCode
        GROUP BY
            e.StageEventId,
            e.PlantCode,
            e.WorkCenterCode,
            e.LotNumber,
            e.MaterialCode,
            e.EventPriority,
            e.RegionCode,
            e.EscalationTier,
            e.UtilityRiskScore,
            e.LimitPpm,
            e.IsQualityHold,
            e.IsMaintenanceOverdue,
            e.MinutesPastPlannedEnd,
            e.ScrapRankByCenter,
            e.TotalScrapByCenter,
            e.OeePercent,
            e.TemperatureC,
            e.VibrationMmS
    )
    INSERT INTO #QualityAlertQueue
    (
        AlertCategory,
        SeverityCode,
        PlantCode,
        WorkCenterCode,
        LotNumber,
        MaterialCode,
        AlertMessage,
        AlertPayload
    )
    SELECT
        N'CONTROL_TOWER_SIGNAL',
        CASE
            WHEN r.RiskStateCode IN (N'CRITICAL_QUALITY_HOLD', N'PREDICTIVE_MAINTENANCE_BREACH') THEN N'CRITICAL'
            WHEN r.RiskStateCode IN (N'EXTENDED_RUNTIME_BREACH', N'CENTER_YIELD_DEGRADATION') THEN N'HIGH'
            ELSE N'MEDIUM'
        END,
        r.PlantCode,
        r.WorkCenterCode,
        r.LotNumber,
        r.MaterialCode,
        CONCAT(N'Risk state detected for lot ', r.LotNumber, N': ', r.RiskStateCode),
        (
            SELECT
                r.EventPriority AS [priority],
                r.RegionCode AS [region],
                r.EscalationTier AS [tier],
                r.UtilityRiskScore AS [utilityRiskScore],
                r.LimitPpm AS [limitPpm],
                r.MinutesPastPlannedEnd AS [minutesPastPlannedEnd],
                r.BomReachCount AS [bomReachCount],
                r.MaxBomDepth AS [maxBomDepth],
                r.OeePercent AS [oeePercent]
            FOR JSON PATH, WITHOUT_ARRAY_WRAPPER, INCLUDE_NULL_VALUES
        )
    FROM RiskSignals AS r
    WHERE r.RiskStateCode <> N'NORMAL';

    INSERT INTO #CapacityPivotSeed
    (
        PlantCode,
        WorkCenterCode,
        ShiftCode,
        FunctionalHours
    )
    SELECT
        s.PlantCode,
        s.WorkCenterCode,
        s.ShiftCode,
        s.LaborHours + s.MachineHours
    FROM #ProductionEventStage AS s;

    DECLARE @PivotColumns NVARCHAR(MAX);
    DECLARE @PivotSql NVARCHAR(MAX);

    SELECT
        @PivotColumns = STRING_AGG(QUOTENAME(ShiftCode), N',')
    FROM
    (
        SELECT DISTINCT ShiftCode
        FROM #CapacityPivotSeed
    ) AS shifts;

    SET @PivotSql = N'
        SELECT PlantCode, WorkCenterCode, ' + @PivotColumns + N'
        INTO #CapacityMatrix
        FROM
        (
            SELECT PlantCode, WorkCenterCode, ShiftCode, FunctionalHours
            FROM #CapacityPivotSeed
        ) src
        PIVOT
        (
            SUM(FunctionalHours)
            FOR ShiftCode IN (' + @PivotColumns + N')
        ) p;';

    EXEC sys.sp_executesql @PivotSql;

    MERGE INTO dbo.ManufacturingControlTowerSnapshot AS target
    USING
    (
        SELECT
            s.PlantCode,
            s.WorkCenterCode,
            COUNT(*) AS ActiveEventCount,
            SUM(s.UnitsCompleted) AS TotalUnitsCompleted,
            SUM(s.UnitsScrapped) AS TotalUnitsScrapped,
            AVG(s.OeePercent) AS AvgOeePercent,
            MAX(s.EventUtc) AS LastEventUtc,
            SYSUTCDATETIME() AS SnapshotUtc
        FROM #ProductionEventStage AS s
        GROUP BY
            s.PlantCode,
            s.WorkCenterCode
    ) AS source
        ON target.PlantCode = source.PlantCode
       AND target.WorkCenterCode = source.WorkCenterCode
    WHEN MATCHED THEN
        UPDATE SET
            target.ActiveEventCount = source.ActiveEventCount,
            target.TotalUnitsCompleted = source.TotalUnitsCompleted,
            target.TotalUnitsScrapped = source.TotalUnitsScrapped,
            target.AvgOeePercent = source.AvgOeePercent,
            target.LastEventUtc = source.LastEventUtc,
            target.LastRefreshUtc = source.SnapshotUtc
    WHEN NOT MATCHED THEN
        INSERT
        (
            PlantCode,
            WorkCenterCode,
            ActiveEventCount,
            TotalUnitsCompleted,
            TotalUnitsScrapped,
            AvgOeePercent,
            LastEventUtc,
            LastRefreshUtc
        )
        VALUES
        (
            source.PlantCode,
            source.WorkCenterCode,
            source.ActiveEventCount,
            source.TotalUnitsCompleted,
            source.TotalUnitsScrapped,
            source.AvgOeePercent,
            source.LastEventUtc,
            source.SnapshotUtc
        )
    OUTPUT
        $action,
        inserted.PlantCode,
        inserted.WorkCenterCode,
        inserted.LastRefreshUtc
    INTO dbo.ManufacturingControlTowerAudit
    (
        MergeAction,
        PlantCode,
        WorkCenterCode,
        AuditUtc
    );

    IF EXISTS
    (
        SELECT 1
        FROM #QualityAlertQueue
        WHERE SeverityCode = N'CRITICAL'
    )
    BEGIN
        WAITFOR DELAY '00:00:03';
    END;

    DECLARE @DispatchPlantCode AS NVARCHAR(20);
    DECLARE @DispatchWorkCenterCode AS NVARCHAR(30);
    DECLARE @DispatchLotNumber AS NVARCHAR(40);

    DECLARE CriticalAlertCursor CURSOR LOCAL FAST_FORWARD FOR
        SELECT
            q.PlantCode,
            q.WorkCenterCode,
            q.LotNumber
        FROM #QualityAlertQueue AS q
        WHERE q.SeverityCode IN (N'CRITICAL', N'HIGH')
        ORDER BY q.AlertUtc, q.AlertId;

    OPEN CriticalAlertCursor;
    FETCH NEXT FROM CriticalAlertCursor
        INTO @DispatchPlantCode, @DispatchWorkCenterCode, @DispatchLotNumber;

    WHILE @@FETCH_STATUS = 0
    BEGIN
        EXEC dbo.usp_DispatchManufacturingEscalation
            @PlantCode = @DispatchPlantCode,
            @WorkCenterCode = @DispatchWorkCenterCode,
            @LotNumber = @DispatchLotNumber,
            @RequestedUtc = SYSUTCDATETIME();

        FETCH NEXT FROM CriticalAlertCursor
            INTO @DispatchPlantCode, @DispatchWorkCenterCode, @DispatchLotNumber;
    END;

    CLOSE CriticalAlertCursor;
    DEALLOCATE CriticalAlertCursor;

    INSERT INTO dbo.ManufacturingControlTowerRuns
    (
        RunUtc,
        RunCategory,
        FinalStateCode,
        AlertEnvelopeJson,
        LineageEnvelopeXml
    )
    SELECT
        SYSUTCDATETIME(),
        N'MANUFACTURING_CONTROL_TOWER',
        CASE
            WHEN EXISTS (SELECT 1 FROM #QualityAlertQueue WHERE SeverityCode = N'CRITICAL') THEN N'ESCALATED'
            WHEN EXISTS (SELECT 1 FROM #QualityAlertQueue) THEN N'WARNINGS'
            ELSE N'CLEAR'
        END,
        (
            SELECT
                q.AlertCategory,
                q.SeverityCode,
                q.PlantCode,
                q.WorkCenterCode,
                q.LotNumber,
                q.MaterialCode,
                q.AlertMessage
            FROM #QualityAlertQueue AS q
            FOR JSON PATH, INCLUDE_NULL_VALUES
        ),
        (
            SELECT
                g.LotNumber AS [@lotNumber],
                g.ParentLotNumber AS [@parentLotNumber],
                g.HierarchyLevel AS [@level],
                g.TraversalPath AS [path]
            FROM #LineageGraph AS g
            FOR XML PATH('lot'), ROOT('lineage'), TYPE
        );

    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    IF CURSOR_STATUS('local', 'CriticalAlertCursor') >= -1
    BEGIN
        CLOSE CriticalAlertCursor;
        DEALLOCATE CriticalAlertCursor;
    END;

    IF XACT_STATE() = -1
        ROLLBACK TRANSACTION;
    ELSE IF XACT_STATE() = 1
        ROLLBACK TRANSACTION BeforeControlTowerEvaluation;

    INSERT INTO #QualityAlertQueue
    (
        AlertCategory,
        SeverityCode,
        PlantCode,
        WorkCenterCode,
        LotNumber,
        MaterialCode,
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
    q.PlantCode,
    q.WorkCenterCode,
    q.LotNumber,
    q.MaterialCode,
    q.AlertMessage,
    q.AlertPayload
FROM #QualityAlertQueue AS q
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
    g.GraphRowId,
    g.LotNumber,
    g.ParentLotNumber,
    g.HierarchyLevel,
    g.TraversalPath
FROM #LineageGraph AS g
ORDER BY
    g.LotNumber,
    g.HierarchyLevel;

DROP TABLE IF EXISTS #CapacityMatrix;
DROP TABLE IF EXISTS #CapacityPivotSeed;
DROP TABLE IF EXISTS #LineageGraph;
DROP TABLE IF EXISTS #QualityAlertQueue;
DROP TABLE IF EXISTS #ProductionEventStage;
GO

EXEC dbo.usp_FinalizeManufacturingControlTowerWindow
    @WindowCode = N'GLOBAL_MFG_CONTROL_TOWER',
    @ClosedUtc = SYSUTCDATETIME(),
    @ClosedBy = ORIGINAL_LOGIN();
