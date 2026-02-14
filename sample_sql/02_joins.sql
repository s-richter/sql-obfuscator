-- SELECT with INNER JOIN and LEFT JOIN
SELECT 
    u.UserId,
    u.UserName,
    o.OrderId,
    o.OrderTotal,
    p.ProductName,
    od.Quantity
FROM Users u
INNER JOIN Orders o ON u.UserId = o.UserId
LEFT JOIN OrderDetails od ON o.OrderId = od.OrderId
LEFT JOIN Products p ON od.ProductId = p.ProductId
WHERE o.OrderDate >= '2025-06-01'
  AND u.Status = 'Active'
ORDER BY o.OrderDate DESC;
