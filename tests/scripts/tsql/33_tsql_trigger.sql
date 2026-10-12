CREATE TRIGGER dbo.trg_Orders_Audit
ON dbo.Orders
AFTER INSERT, UPDATE, DELETE
AS
BEGIN
    SET NOCOUNT ON;

    INSERT INTO audit.OrderChanges (OrderId, ChangeType, OldTotal, NewTotal, ChangedAt, ChangedBy)
    SELECT
        COALESCE(i.OrderId, d.OrderId),
        CASE
            WHEN i.OrderId IS NOT NULL AND d.OrderId IS NOT NULL THEN 'U'
            WHEN i.OrderId IS NOT NULL THEN 'I'
            ELSE 'D'
        END,
        d.Total,
        i.Total,
        SYSUTCDATETIME(),
        SUSER_SNAME()
    FROM inserted AS i
    FULL OUTER JOIN deleted AS d ON d.OrderId = i.OrderId;

    IF UPDATE(Total)
        UPDATE o SET o.LastRepricedAt = GETDATE()
        FROM dbo.Orders AS o
        JOIN inserted AS i ON i.OrderId = o.OrderId;
END
GO
