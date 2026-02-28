-- Extreme T-SQL stress sample 2
-- Purpose: financial reconciliation workflow with temp tables, recursive CTEs, snapshots,
-- savepoints, cursor processing, dynamic pivoting, JSON/XML generation, grouping sets,
-- window functions, and multi-batch close-window patterns.

SET NOCOUNT ON;
SET ARITHABORT ON;
SET DATEFIRST 1;

IF OBJECT_ID('tempdb..#LedgerStage') IS NOT NULL
    DROP TABLE #LedgerStage;

IF OBJECT_ID('tempdb..#ReconExceptions') IS NOT NULL
    DROP TABLE #ReconExceptions;

CREATE TABLE #LedgerStage
(
    LedgerStageId BIGINT IDENTITY(1, 1) PRIMARY KEY,
    AccountNumber NVARCHAR(40) NOT NULL,
    SubLedgerCode NVARCHAR(30) NOT NULL,
    BusinessUnitCode NVARCHAR(20) NOT NULL,
    LegalEntityCode NVARCHAR(20) NOT NULL,
    CurrencyCode CHAR(3) NOT NULL,
    FiscalYear SMALLINT NOT NULL,
    FiscalPeriod TINYINT NOT NULL,
    PostingDate DATE NOT NULL,
    DocumentDate DATE NOT NULL,
    JournalId BIGINT NOT NULL,
    LineNumber INT NOT NULL,
    JournalType NVARCHAR(30) NOT NULL,
    SourceModule NVARCHAR(30) NOT NULL,
    CounterpartyCode NVARCHAR(40) NULL,
    CostCenterCode NVARCHAR(30) NULL,
    ProjectCode NVARCHAR(30) NULL,
    DebitAmount DECIMAL(19, 4) NOT NULL,
    CreditAmount DECIMAL(19, 4) NOT NULL,
    FunctionalAmount AS (DebitAmount - CreditAmount) PERSISTED,
    LocalAmount DECIMAL(19, 4) NOT NULL,
    ExchangeRate DECIMAL(19, 8) NOT NULL,
    ReversalFlag BIT NOT NULL,
    ApprovalState NVARCHAR(20) NOT NULL,
    PayloadJson NVARCHAR(MAX) NULL,
    CreatedUtc DATETIME2(3) NOT NULL DEFAULT SYSUTCDATETIME()
);

CREATE TABLE #ReconExceptions
(
    ExceptionId BIGINT IDENTITY(1, 1) PRIMARY KEY,
    ExceptionCategory NVARCHAR(50) NOT NULL,
    SeverityCode NVARCHAR(20) NOT NULL,
    AccountNumber NVARCHAR(40) NULL,
    JournalId BIGINT NULL,
    LineNumber INT NULL,
    ExceptionMessage NVARCHAR(4000) NOT NULL,
    DiagnosticJson NVARCHAR(MAX) NULL,
    CreatedUtc DATETIME2(3) NOT NULL DEFAULT SYSUTCDATETIME()
);

DECLARE @SourceLedger TABLE
(
    RowId INT IDENTITY(1, 1) PRIMARY KEY,
    AccountNumber NVARCHAR(40) NOT NULL,
    SubLedgerCode NVARCHAR(30) NOT NULL,
    BusinessUnitCode NVARCHAR(20) NOT NULL,
    LegalEntityCode NVARCHAR(20) NOT NULL,
    CurrencyCode CHAR(3) NOT NULL,
    FiscalYear SMALLINT NOT NULL,
    FiscalPeriod TINYINT NOT NULL,
    PostingDate DATE NOT NULL,
    DocumentDate DATE NOT NULL,
    JournalId BIGINT NOT NULL,
    LineNumber INT NOT NULL,
    JournalType NVARCHAR(30) NOT NULL,
    SourceModule NVARCHAR(30) NOT NULL,
    CounterpartyCode NVARCHAR(40) NULL,
    CostCenterCode NVARCHAR(30) NULL,
    ProjectCode NVARCHAR(30) NULL,
    DebitAmount DECIMAL(19, 4) NOT NULL,
    CreditAmount DECIMAL(19, 4) NOT NULL,
    LocalAmount DECIMAL(19, 4) NOT NULL,
    ExchangeRate DECIMAL(19, 8) NOT NULL,
    ReversalFlag BIT NOT NULL,
    ApprovalState NVARCHAR(20) NOT NULL,
    PayloadJson NVARCHAR(MAX) NULL
);

INSERT INTO @SourceLedger
(
    AccountNumber,
    SubLedgerCode,
    BusinessUnitCode,
    LegalEntityCode,
    CurrencyCode,
    FiscalYear,
    FiscalPeriod,
    PostingDate,
    DocumentDate,
    JournalId,
    LineNumber,
    JournalType,
    SourceModule,
    CounterpartyCode,
    CostCenterCode,
    ProjectCode,
    DebitAmount,
    CreditAmount,
    LocalAmount,
    ExchangeRate,
    ReversalFlag,
    ApprovalState,
    PayloadJson
)
VALUES
    (N'1100-AR', N'AR', N'BU01', N'LE01', N'USD', 2025, 10, '2025-10-01', '2025-09-30', 9000001, 1, N'INVOICE', N'BILLING', N'CUST-100', N'CC-001', N'PRJ-RED', 15000.00, 0.00, 15000.00, 1.00000000, 0, N'APPROVED', N'{"source":"invoice","docNo":"INV-9000001","tags":["month-end"]}'),
    (N'1100-AR', N'AR', N'BU01', N'LE01', N'USD', 2025, 10, '2025-10-01', '2025-09-30', 9000001, 2, N'INVOICE', N'BILLING', N'CUST-100', N'CC-001', N'PRJ-RED', 0.00, 15000.00, -15000.00, 1.00000000, 0, N'APPROVED', N'{"source":"invoice-offset","docNo":"INV-9000001","tags":["month-end"]}'),
    (N'2100-AP', N'AP', N'BU02', N'LE01', N'EUR', 2025, 10, '2025-10-03', '2025-10-02', 9000002, 1, N'VOUCHER', N'PAYABLES', N'VEND-220', N'CC-203', N'PRJ-BLUE', 0.00, 8200.00, -8200.00, 1.08450000, 0, N'PENDING', N'{"source":"voucher","docNo":"VCH-9000002","tags":["approval"]}'),
    (N'5100-EXP', N'GL', N'BU02', N'LE01', N'EUR', 2025, 10, '2025-10-03', '2025-10-02', 9000002, 2, N'VOUCHER', N'PAYABLES', N'VEND-220', N'CC-203', N'PRJ-BLUE', 8200.00, 0.00, 8200.00, 1.08450000, 0, N'PENDING', N'{"source":"voucher-expense","docNo":"VCH-9000002","tags":["approval"]}'),
    (N'1300-CASH', N'TR', N'BU03', N'LE02', N'GBP', 2025, 10, '2025-10-04', '2025-10-04', 9000003, 1, N'TRANSFER', N'TREASURY', N'BANK-01', N'CC-901', N'PRJ-GOLD', 0.00, 500000.00, -500000.00, 1.26780000, 0, N'APPROVED', N'{"source":"transfer","docNo":"TRF-9000003","tags":["treasury","high-value"]}'),
    (N'1300-CASH', N'TR', N'BU03', N'LE02', N'GBP', 2025, 10, '2025-10-04', '2025-10-04', 9000003, 2, N'TRANSFER', N'TREASURY', N'BANK-02', N'CC-901', N'PRJ-GOLD', 500000.00, 0.00, 500000.00, 1.26780000, 0, N'APPROVED', N'{"source":"transfer","docNo":"TRF-9000003","tags":["treasury","high-value"]}'),
    (N'9999-SUSPENSE', N'GL', N'BU99', N'LE09', N'USD', 2025, 10, '2025-10-05', '2025-10-05', 9000004, 1, N'ADJUSTMENT', N'MANUAL', NULL, N'CC-999', NULL, 100.00, 0.00, 100.00, 1.00000000, 0, N'REJECTED', N'{"source":"manual","docNo":"ADJ-9000004","tags":["exception"]}');

INSERT INTO #LedgerStage
(
    AccountNumber,
    SubLedgerCode,
    BusinessUnitCode,
    LegalEntityCode,
    CurrencyCode,
    FiscalYear,
    FiscalPeriod,
    PostingDate,
    DocumentDate,
    JournalId,
    LineNumber,
    JournalType,
    SourceModule,
    CounterpartyCode,
    CostCenterCode,
    ProjectCode,
    DebitAmount,
    CreditAmount,
    LocalAmount,
    ExchangeRate,
    ReversalFlag,
    ApprovalState,
    PayloadJson
)
SELECT
    s.AccountNumber,
    s.SubLedgerCode,
    s.BusinessUnitCode,
    s.LegalEntityCode,
    s.CurrencyCode,
    s.FiscalYear,
    s.FiscalPeriod,
    s.PostingDate,
    s.DocumentDate,
    s.JournalId,
    s.LineNumber,
    s.JournalType,
    s.SourceModule,
    s.CounterpartyCode,
    s.CostCenterCode,
    s.ProjectCode,
    s.DebitAmount,
    s.CreditAmount,
    s.LocalAmount,
    s.ExchangeRate,
    s.ReversalFlag,
    s.ApprovalState,
    s.PayloadJson
FROM @SourceLedger s;

BEGIN TRY
    BEGIN TRANSACTION;

    SAVE TRANSACTION BeforeReconChecks;

    ;WITH JournalNetting AS
    (
        SELECT
            ls.JournalId,
            SUM(ls.DebitAmount) AS TotalDebit,
            SUM(ls.CreditAmount) AS TotalCredit,
            SUM(ls.FunctionalAmount) AS NetFunctionalAmount,
            COUNT(*) AS LineCount
        FROM #LedgerStage ls
        GROUP BY ls.JournalId
    ),
    JournalValidation AS
    (
        SELECT
            jn.JournalId,
            jn.TotalDebit,
            jn.TotalCredit,
            jn.NetFunctionalAmount,
            jn.LineCount,
            CASE
                WHEN ABS(jn.NetFunctionalAmount) > 0.005 THEN N'OUT_OF_BALANCE'
                WHEN jn.LineCount < 2 THEN N'INCOMPLETE'
                ELSE N'VALID'
            END AS JournalState
        FROM JournalNetting jn
    )
    INSERT INTO #ReconExceptions
    (
        ExceptionCategory,
        SeverityCode,
        AccountNumber,
        JournalId,
        LineNumber,
        ExceptionMessage,
        DiagnosticJson
    )
    SELECT
        N'JOURNAL_VALIDATION',
        CASE WHEN jv.JournalState = N'OUT_OF_BALANCE' THEN N'CRITICAL' ELSE N'WARNING' END,
        NULL,
        jv.JournalId,
        NULL,
        CONCAT(N'Journal state is ', jv.JournalState),
        CONCAT(
            N'{"totalDebit":', CONVERT(NVARCHAR(50), jv.TotalDebit),
            N',"totalCredit":', CONVERT(NVARCHAR(50), jv.TotalCredit),
            N',"lineCount":', jv.LineCount, N'}'
        )
    FROM JournalValidation jv
    WHERE jv.JournalState <> N'VALID';

    ;WITH LedgerEnriched AS
    (
        SELECT
            ls.LedgerStageId,
            ls.AccountNumber,
            ls.SubLedgerCode,
            ls.BusinessUnitCode,
            ls.LegalEntityCode,
            ls.CurrencyCode,
            ls.FiscalYear,
            ls.FiscalPeriod,
            ls.PostingDate,
            ls.JournalId,
            ls.LineNumber,
            ls.JournalType,
            ls.SourceModule,
            ls.CounterpartyCode,
            ls.CostCenterCode,
            ls.ProjectCode,
            ls.DebitAmount,
            ls.CreditAmount,
            ls.FunctionalAmount,
            ls.LocalAmount,
            ls.ExchangeRate,
            ls.ReversalFlag,
            ls.ApprovalState,
            JSON_VALUE(ls.PayloadJson, '$.source') AS PayloadSource,
            JSON_VALUE(ls.PayloadJson, '$.docNo') AS DocumentNumber,
            SUM(ls.FunctionalAmount) OVER (
                PARTITION BY ls.AccountNumber, ls.FiscalYear, ls.FiscalPeriod
            ) AS AccountPeriodNet,
            AVG(ABS(ls.FunctionalAmount)) OVER (
                PARTITION BY ls.AccountNumber
            ) AS AverageAbsoluteLineValue,
            ROW_NUMBER() OVER (
                PARTITION BY ls.AccountNumber
                ORDER BY ABS(ls.FunctionalAmount) DESC, ls.JournalId DESC, ls.LineNumber DESC
            ) AS AccountImpactRank
        FROM #LedgerStage ls
    ),
    Hierarchy AS
    (
        SELECT
            le.AccountNumber,
            le.SubLedgerCode,
            CAST(le.AccountNumber AS NVARCHAR(4000)) AS AccountPath,
            0 AS Depth
        FROM LedgerEnriched le
        WHERE le.AccountNumber LIKE N'%-%'

        UNION ALL

        SELECT
            h.AccountNumber,
            LEFT(h.SubLedgerCode, LEN(h.SubLedgerCode) - 1),
            CAST(h.AccountPath + N'>' + LEFT(h.SubLedgerCode, LEN(h.SubLedgerCode) - 1) AS NVARCHAR(4000)),
            h.Depth + 1
        FROM Hierarchy h
        WHERE LEN(h.SubLedgerCode) > 1
    ),
    SummaryWithGrouping AS
    (
        SELECT
            le.BusinessUnitCode,
            le.LegalEntityCode,
            le.CurrencyCode,
            le.AccountNumber,
            SUM(le.DebitAmount) AS DebitAmount,
            SUM(le.CreditAmount) AS CreditAmount,
            SUM(le.FunctionalAmount) AS FunctionalAmount,
            GROUPING(le.BusinessUnitCode) AS IsBusinessUnitAggregate,
            GROUPING(le.LegalEntityCode) AS IsLegalEntityAggregate,
            GROUPING(le.CurrencyCode) AS IsCurrencyAggregate,
            GROUPING(le.AccountNumber) AS IsAccountAggregate
        FROM LedgerEnriched le
        GROUP BY GROUPING SETS
        (
            (le.BusinessUnitCode, le.LegalEntityCode, le.CurrencyCode, le.AccountNumber),
            (le.BusinessUnitCode, le.LegalEntityCode, le.CurrencyCode),
            (le.BusinessUnitCode, le.LegalEntityCode),
            ()
        )
    )
    SELECT
        swg.BusinessUnitCode,
        swg.LegalEntityCode,
        swg.CurrencyCode,
        swg.AccountNumber,
        swg.DebitAmount,
        swg.CreditAmount,
        swg.FunctionalAmount,
        swg.IsBusinessUnitAggregate,
        swg.IsLegalEntityAggregate,
        swg.IsCurrencyAggregate,
        swg.IsAccountAggregate
    INTO #ReconSummary
    FROM SummaryWithGrouping swg;

    DECLARE @AccountNumber NVARCHAR(40);
    DECLARE @JournalId BIGINT;
    DECLARE @FunctionalAmount DECIMAL(19, 4);

    DECLARE HighImpactCursor CURSOR LOCAL FAST_FORWARD FOR
        SELECT
            le.AccountNumber,
            le.JournalId,
            le.FunctionalAmount
        FROM
        (
            SELECT
                ls.AccountNumber,
                ls.JournalId,
                ls.FunctionalAmount,
                ROW_NUMBER() OVER (
                    PARTITION BY ls.AccountNumber
                    ORDER BY ABS(ls.FunctionalAmount) DESC, ls.JournalId DESC
                ) AS rn
            FROM #LedgerStage ls
        ) le
        WHERE le.rn <= 2;

    OPEN HighImpactCursor;
    FETCH NEXT FROM HighImpactCursor INTO @AccountNumber, @JournalId, @FunctionalAmount;

    WHILE @@FETCH_STATUS = 0
    BEGIN
        IF ABS(@FunctionalAmount) >= 100000.00
        BEGIN
            INSERT INTO #ReconExceptions
            (
                ExceptionCategory,
                SeverityCode,
                AccountNumber,
                JournalId,
                LineNumber,
                ExceptionMessage,
                DiagnosticJson
            )
            VALUES
            (
                N'HIGH_IMPACT_LINE',
                N'CRITICAL',
                @AccountNumber,
                @JournalId,
                NULL,
                N'High impact journal line requires treasury review.',
                CONCAT(N'{"functionalAmount":', CONVERT(NVARCHAR(50), @FunctionalAmount), N'}')
            );
        END;

        FETCH NEXT FROM HighImpactCursor INTO @AccountNumber, @JournalId, @FunctionalAmount;
    END;

    CLOSE HighImpactCursor;
    DEALLOCATE HighImpactCursor;

    DECLARE @DynamicColumns NVARCHAR(MAX);
    DECLARE @DynamicPivotSql NVARCHAR(MAX);

    SELECT
        @DynamicColumns = STRING_AGG(QUOTENAME(CurrencyCode), N',')
    FROM
    (
        SELECT DISTINCT CurrencyCode
        FROM #LedgerStage
    ) c;

    SET @DynamicPivotSql = N'
        SELECT AccountNumber, ' + @DynamicColumns + N'
        INTO #CurrencyPivot
        FROM
        (
            SELECT AccountNumber, CurrencyCode, FunctionalAmount
            FROM #LedgerStage
        ) src
        PIVOT
        (
            SUM(FunctionalAmount)
            FOR CurrencyCode IN (' + @DynamicColumns + N')
        ) p;';

    EXEC sys.sp_executesql @DynamicPivotSql;

    INSERT INTO dbo.ReconciliationRunLog
    (
        RunUtc,
        RunType,
        StatusCode,
        SummaryJson,
        SummaryXml
    )
    SELECT
        SYSUTCDATETIME(),
        N'FINANCIAL_RECON',
        CASE WHEN EXISTS (SELECT 1 FROM #ReconExceptions WHERE SeverityCode = N'CRITICAL') THEN N'FAILED' ELSE N'COMPLETED' END,
        (
            SELECT
                rs.BusinessUnitCode,
                rs.LegalEntityCode,
                rs.CurrencyCode,
                rs.AccountNumber,
                rs.FunctionalAmount
            FROM #ReconSummary rs
            FOR JSON PATH, INCLUDE_NULL_VALUES
        ),
        (
            SELECT
                re.ExceptionCategory AS [@category],
                re.SeverityCode AS [@severity],
                re.AccountNumber AS [account],
                re.JournalId AS [journalId],
                re.ExceptionMessage AS [message]
            FROM #ReconExceptions re
            FOR XML PATH('exception'), ROOT('exceptions'), TYPE
        );

    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    IF CURSOR_STATUS('local', 'HighImpactCursor') >= -1
    BEGIN
        CLOSE HighImpactCursor;
        DEALLOCATE HighImpactCursor;
    END;

    IF XACT_STATE() = -1
        ROLLBACK TRANSACTION;
    ELSE IF XACT_STATE() = 1
        ROLLBACK TRANSACTION BeforeReconChecks;

    INSERT INTO #ReconExceptions
    (
        ExceptionCategory,
        SeverityCode,
        AccountNumber,
        JournalId,
        LineNumber,
        ExceptionMessage,
        DiagnosticJson
    )
    VALUES
    (
        N'RUNTIME_ERROR',
        N'CRITICAL',
        NULL,
        NULL,
        NULL,
        ERROR_MESSAGE(),
        CONCAT(
            N'{"errorNumber":', ERROR_NUMBER(),
            N',"line":', ERROR_LINE(),
            N',"state":', ERROR_STATE(), N'}'
        )
    );

    THROW;
END CATCH;

SELECT
    ls.BusinessUnitCode,
    ls.LegalEntityCode,
    ls.CurrencyCode,
    COUNT(*) AS LineCount,
    SUM(ls.DebitAmount) AS DebitAmount,
    SUM(ls.CreditAmount) AS CreditAmount,
    SUM(ls.FunctionalAmount) AS FunctionalNetAmount,
    MIN(ls.PostingDate) AS FirstPostingDate,
    MAX(ls.PostingDate) AS LastPostingDate
FROM #LedgerStage ls
GROUP BY
    ls.BusinessUnitCode,
    ls.LegalEntityCode,
    ls.CurrencyCode
HAVING ABS(SUM(ls.FunctionalAmount)) >= 0.00
ORDER BY
    ls.BusinessUnitCode,
    ls.LegalEntityCode,
    ls.CurrencyCode;

SELECT
    re.ExceptionId,
    re.ExceptionCategory,
    re.SeverityCode,
    re.AccountNumber,
    re.JournalId,
    re.ExceptionMessage,
    re.DiagnosticJson,
    re.CreatedUtc
FROM #ReconExceptions re
ORDER BY
    CASE re.SeverityCode
        WHEN N'CRITICAL' THEN 1
        WHEN N'WARNING' THEN 2
        ELSE 3
    END,
    re.CreatedUtc DESC;

DROP TABLE IF EXISTS #CurrencyPivot;
DROP TABLE IF EXISTS #ReconSummary;
DROP TABLE IF EXISTS #ReconExceptions;
DROP TABLE IF EXISTS #LedgerStage;
GO

WAITFOR DELAY '00:00:01';
GO

EXEC dbo.usp_FinalizeReconciliationWindow
    @WindowName = N'MONTH_END_CLOSE',
    @CompletedUtc = SYSUTCDATETIME(),
    @CompletedBy = ORIGINAL_LOGIN();
