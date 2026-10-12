-- Schema-qualified tables and subqueries
SELECT 
    u.UserId,
    u.UserName,
    dbo.Users.EmailAddress,
    (SELECT COUNT(*) 
     FROM dbo.Orders o 
     WHERE o.UserId = u.UserId) AS OrderCount,
    (SELECT SUM(OrderTotal) 
     FROM dbo.Orders o2 
     WHERE o2.UserId = u.UserId) AS TotalSpent
FROM dbo.Users u
WHERE u.UserId IN (
    SELECT DISTINCT o.UserId
    FROM dbo.Orders o
    WHERE o.OrderDate >= '2025-01-01'
      AND o.OrderTotal > 100
)
  AND u.Status = 'Active'
ORDER BY TotalSpent DESC;
