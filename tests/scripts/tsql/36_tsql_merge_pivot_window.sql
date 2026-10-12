MERGE INTO dw.DimCustomer AS tgt
USING staging.Customer AS src
    ON tgt.CustomerKey = src.CustomerKey
WHEN MATCHED AND (tgt.Segment <> src.Segment OR tgt.Email <> src.Email) THEN
    UPDATE SET tgt.Segment = src.Segment, tgt.Email = src.Email, tgt.UpdatedAt = SYSUTCDATETIME()
WHEN NOT MATCHED BY TARGET THEN
    INSERT (CustomerKey, Segment, Email, UpdatedAt)
    VALUES (src.CustomerKey, src.Segment, src.Email, SYSUTCDATETIME())
WHEN NOT MATCHED BY SOURCE THEN
    DELETE
OUTPUT $action, inserted.CustomerKey, deleted.CustomerKey INTO audit.MergeLog (ActionName, NewKey, OldKey);

SELECT p.Region, p.[2023], p.[2024], p.[2025]
FROM (
    SELECT s.Region, YEAR(s.SoldOn) AS SalesYear, s.Amount
    FROM dw.FactSales AS s
) AS x
PIVOT (SUM(x.Amount) FOR x.SalesYear IN ([2023], [2024], [2025])) AS p;

SELECT u.CustomerKey, u.Channel, u.Spend
FROM dw.ChannelSpend AS cs
UNPIVOT (Spend FOR Channel IN (WebSpend, StoreSpend, PhoneSpend)) AS u;

WITH ranked AS (
    SELECT
        s.CustomerKey,
        s.Amount,
        ROW_NUMBER() OVER (PARTITION BY s.CustomerKey ORDER BY s.SoldOn DESC) AS rn,
        SUM(s.Amount) OVER (PARTITION BY s.CustomerKey ORDER BY s.SoldOn
                            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS RunningTotal,
        LAG(s.Amount, 1, 0) OVER (PARTITION BY s.CustomerKey ORDER BY s.SoldOn) AS PreviousAmount
    FROM dw.FactSales AS s
),
latest AS (
    SELECT CustomerKey, Amount, RunningTotal FROM ranked WHERE rn = 1
)
SELECT l.CustomerKey, l.Amount, l.RunningTotal, STRING_AGG(d.Segment, ', ') WITHIN GROUP (ORDER BY d.Segment) AS Segments
FROM latest AS l
JOIN dw.DimCustomer AS d ON d.CustomerKey = l.CustomerKey
GROUP BY l.CustomerKey, l.Amount, l.RunningTotal
HAVING SUM(l.Amount) > 0
ORDER BY l.RunningTotal DESC
OFFSET 20 ROWS FETCH NEXT 10 ROWS ONLY
OPTION (RECOMPILE, MAXDOP 2);
