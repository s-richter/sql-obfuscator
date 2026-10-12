-- CTE (Common Table Expression) example
WITH CustomerOrders AS (
    SELECT 
        UserId,
        COUNT(*) AS OrderCount,
        SUM(OrderTotal) AS TotalAmount
    FROM Orders
    GROUP BY UserId
),
TopCustomers AS (
    SELECT 
        UserId,
        OrderCount,
        TotalAmount,
        ROW_NUMBER() OVER (ORDER BY TotalAmount DESC) AS Rank
    FROM CustomerOrders
    WHERE OrderCount >= 3
)
SELECT 
    u.UserName,
    u.EmailAddress,
    tc.OrderCount,
    tc.TotalAmount,
    tc.Rank
FROM TopCustomers tc
INNER JOIN Users u ON tc.UserId = u.UserId
WHERE tc.Rank <= 10;
