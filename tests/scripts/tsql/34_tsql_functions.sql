CREATE FUNCTION dbo.fn_NetAmount (@Gross DECIMAL(18, 2), @TaxRate DECIMAL(5, 4))
RETURNS DECIMAL(18, 2)
AS
BEGIN
    DECLARE @Net DECIMAL(18, 2);
    SET @Net = @Gross / (1 + @TaxRate);
    RETURN ROUND(@Net, 2);
END
GO

CREATE FUNCTION dbo.fn_OrdersForCustomer (@CustomerId INT, @Since DATE)
RETURNS TABLE
AS
RETURN
(
    SELECT o.OrderId, o.OrderDate, dbo.fn_NetAmount(o.Total, 0.25) AS NetTotal
    FROM dbo.Orders AS o
    WHERE o.CustomerId = @CustomerId
      AND o.OrderDate >= @Since
);
GO

CREATE FUNCTION dbo.fn_TopProducts (@Limit INT)
RETURNS @Result TABLE (ProductId INT PRIMARY KEY, Revenue MONEY)
AS
BEGIN
    INSERT INTO @Result (ProductId, Revenue)
    SELECT TOP (@Limit) l.ProductId, SUM(l.Quantity * l.UnitPrice)
    FROM dbo.OrderLines AS l
    GROUP BY l.ProductId
    ORDER BY SUM(l.Quantity * l.UnitPrice) DESC;
    RETURN;
END
GO

SELECT c.CustomerId, f.OrderId, f.NetTotal
FROM dbo.Customers AS c
CROSS APPLY dbo.fn_OrdersForCustomer(c.CustomerId, '2024-01-01') AS f
OUTER APPLY (SELECT TOP 1 t.ProductId FROM dbo.fn_TopProducts(10) AS t) AS best;
