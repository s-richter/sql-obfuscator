-- Temporary table example
CREATE TABLE #TempOrders
(
  OrderId INT,
  UserId INT,
  OrderDate DATE,
  OrderTotal DECIMAL(10, 2),
  Status VARCHAR(50)
);

INSERT INTO #TempOrders
  (OrderId, UserId, OrderDate, OrderTotal, Status)
SELECT OrderId, UserId, OrderDate, OrderTotal, Status
FROM Orders
WHERE OrderDate >= '2025-01-01';

SELECT
  u.UserName,
  COUNT(*) AS OrderCount,
  AVG(t.OrderTotal) AS AvgOrderAmount
FROM #TempOrders t
  INNER JOIN Users u ON t.UserId = u.UserId
WHERE t.Status = 'Completed'
GROUP BY u.UserName
HAVING COUNT(*) > 2
ORDER BY AvgOrderAmount DESC;

DROP TABLE #TempOrders;
