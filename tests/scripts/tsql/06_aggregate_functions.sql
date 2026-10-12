-- Aggregate functions and GROUP BY
SELECT 
    u.UserName,
    u.City,
    COUNT(DISTINCT o.OrderId) AS TotalOrders,
    SUM(o.OrderTotal) AS TotalAmount,
    AVG(o.OrderTotal) AS AvgOrderAmount,
    MIN(o.OrderDate) AS FirstOrderDate,
    MAX(o.OrderDate) AS LastOrderDate
FROM Users u
LEFT JOIN Orders o ON u.UserId = o.UserId
WHERE u.Status = 'Active'
  AND o.OrderDate >= '2024-01-01'
GROUP BY u.UserId, u.UserName, u.City
HAVING COUNT(DISTINCT o.OrderId) >= 5
ORDER BY TotalAmount DESC;
