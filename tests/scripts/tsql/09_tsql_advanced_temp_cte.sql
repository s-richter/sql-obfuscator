-- Advanced T-SQL sample with temp tables, nested subqueries, window functions, and multiple batches
CREATE TABLE #RecentOrders
(
    OrderId INT,
    UserId INT,
    RegionId INT,
    OrderDate DATE,
    OrderTotal DECIMAL(18, 2),
    SalesChannel VARCHAR(50)
);

INSERT INTO #RecentOrders
    (OrderId, UserId, RegionId, OrderDate, OrderTotal, SalesChannel)
SELECT
    o.OrderId,
    o.UserId,
    o.RegionId,
    o.OrderDate,
    o.OrderTotal,
    o.SalesChannel
FROM Orders o
WHERE o.OrderDate >= DATEADD(DAY, -90, GETDATE())
  AND o.OrderTotal > (
      SELECT AVG(o2.OrderTotal)
      FROM Orders o2
      WHERE o2.UserId = o.UserId
  );

GO

WITH RankedOrders AS (
    SELECT
        r.UserId,
        r.RegionId,
        r.OrderId,
        r.OrderDate,
        r.OrderTotal,
        ROW_NUMBER() OVER (
            PARTITION BY r.UserId
            ORDER BY r.OrderTotal DESC, r.OrderDate DESC
        ) AS OrderRank
    FROM #RecentOrders r
),
UserSpend AS (
    SELECT
        ro.UserId,
        COUNT(*) AS OrderCount,
        SUM(ro.OrderTotal) AS TotalSpend,
        MAX(ro.OrderDate) AS LatestOrderDate
    FROM RankedOrders ro
    GROUP BY ro.UserId
),
FlaggedUsers AS (
    SELECT
        us.UserId,
        us.OrderCount,
        us.TotalSpend,
        us.LatestOrderDate
    FROM UserSpend us
    WHERE us.TotalSpend >= 1000
       OR EXISTS (
           SELECT 1
           FROM RankedOrders ro2
           WHERE ro2.UserId = us.UserId
             AND ro2.OrderRank = 1
             AND ro2.OrderTotal >= 500
       )
)
SELECT
    u.UserName,
    reg.RegionName,
    fu.OrderCount,
    fu.TotalSpend,
    fu.LatestOrderDate,
    top_order.OrderId AS HighestValueOrderId,
    top_order.OrderTotal AS HighestValueOrderTotal
FROM FlaggedUsers fu
INNER JOIN Users u
    ON fu.UserId = u.UserId
LEFT JOIN (
    SELECT
        ro.UserId,
        ro.RegionId,
        ro.OrderId,
        ro.OrderTotal
    FROM RankedOrders ro
    WHERE ro.OrderRank = 1
) top_order
    ON fu.UserId = top_order.UserId
LEFT JOIN Regions reg
    ON top_order.RegionId = reg.RegionId
WHERE u.Status IN (
    SELECT s.StatusCode
    FROM UserStatusLookup s
    WHERE s.IsActive = 1
)
ORDER BY fu.TotalSpend DESC, u.UserName ASC;

GO

DROP TABLE #RecentOrders;
