SELECT o.OrderId, o.Total
FROM dbo.Orders AS o -- Windows line endings
WHERE o.Status = 'OPEN'
  AND o.Note = 'line one
line two';
GO
