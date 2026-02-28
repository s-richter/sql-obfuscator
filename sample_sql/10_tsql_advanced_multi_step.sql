-- Advanced T-SQL sample with staging tables, CTE chains, updates, and correlated subqueries
CREATE TABLE #InvoiceStage
(
    InvoiceId INT,
    AccountId INT,
    BillingMonth DATE,
    InvoiceAmount DECIMAL(18, 2),
    PaymentAmount DECIMAL(18, 2),
    BalanceAmount DECIMAL(18, 2),
    RiskBand VARCHAR(20)
);

INSERT INTO #InvoiceStage
    (InvoiceId, AccountId, BillingMonth, InvoiceAmount, PaymentAmount, BalanceAmount, RiskBand)
SELECT
    i.InvoiceId,
    i.AccountId,
    i.BillingMonth,
    i.InvoiceAmount,
    ISNULL(p.PaymentAmount, 0) AS PaymentAmount,
    i.InvoiceAmount - ISNULL(p.PaymentAmount, 0) AS BalanceAmount,
    CASE
        WHEN i.InvoiceAmount - ISNULL(p.PaymentAmount, 0) >= 1000 THEN 'HIGH'
        WHEN i.InvoiceAmount - ISNULL(p.PaymentAmount, 0) >= 250 THEN 'MEDIUM'
        ELSE 'LOW'
    END AS RiskBand
FROM Invoices i
LEFT JOIN (
    SELECT
        InvoiceId,
        SUM(Amount) AS PaymentAmount
    FROM Payments
    WHERE PaymentStatus = 'Posted'
    GROUP BY InvoiceId
) p
    ON i.InvoiceId = p.InvoiceId
WHERE i.BillingMonth >= '2025-01-01';

WITH AccountExposure AS (
    SELECT
        s.AccountId,
        COUNT(*) AS OpenInvoiceCount,
        SUM(s.BalanceAmount) AS TotalBalance,
        MAX(s.BillingMonth) AS LatestBillingMonth
    FROM #InvoiceStage s
    WHERE s.BalanceAmount > 0
    GROUP BY s.AccountId
),
PrioritizedExposure AS (
    SELECT
        ae.AccountId,
        ae.OpenInvoiceCount,
        ae.TotalBalance,
        ae.LatestBillingMonth,
        DENSE_RANK() OVER (
            ORDER BY ae.TotalBalance DESC, ae.OpenInvoiceCount DESC
        ) AS ExposureRank
    FROM AccountExposure ae
),
CollectionCandidates AS (
    SELECT
        pe.AccountId,
        pe.OpenInvoiceCount,
        pe.TotalBalance,
        pe.LatestBillingMonth,
        pe.ExposureRank
    FROM PrioritizedExposure pe
    WHERE pe.ExposureRank <= 25
      AND pe.TotalBalance > (
          SELECT AVG(ae2.TotalBalance)
          FROM AccountExposure ae2
      )
)
UPDATE s
SET s.RiskBand = 'CRITICAL'
FROM #InvoiceStage s
INNER JOIN CollectionCandidates cc
    ON s.AccountId = cc.AccountId
WHERE s.BalanceAmount >= 500;

SELECT
    a.AccountNumber,
    c.AccountId,
    c.OpenInvoiceCount,
    c.TotalBalance,
    c.LatestBillingMonth,
    s.InvoiceId,
    s.BalanceAmount,
    s.RiskBand
FROM CollectionCandidates c
INNER JOIN Accounts a
    ON c.AccountId = a.AccountId
INNER JOIN #InvoiceStage s
    ON c.AccountId = s.AccountId
WHERE s.BalanceAmount = (
    SELECT MAX(s2.BalanceAmount)
    FROM #InvoiceStage s2
    WHERE s2.AccountId = s.AccountId
)
ORDER BY c.ExposureRank ASC, s.BalanceAmount DESC;

DROP TABLE #InvoiceStage;
