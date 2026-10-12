-- Words that switch sqlglot's tokenizer into command mode, each followed by
-- statements with no semicolon in between.
USE Warehouse
GO
SET NOCOUNT ON
SET XACT_ABORT ON
GO

PRINT 'Loading stock levels'
SELECT s.Sku, s.OnHand FROM dbo.StockLevels AS s WHERE s.OnHand < s.ReorderPoint
GO

DECLARE @Sku VARCHAR(20)
DECLARE low_stock CURSOR FOR SELECT Sku FROM dbo.StockLevels WHERE OnHand = 0
OPEN low_stock
FETCH NEXT FROM low_stock INTO @Sku
WHILE @@FETCH_STATUS = 0
BEGIN
    PRINT @Sku
    INSERT INTO dbo.ReorderQueue (Sku) VALUES (@Sku)
    FETCH NEXT FROM low_stock INTO @Sku
END
CLOSE low_stock
DEALLOCATE low_stock
GO

INSERT INTO dbo.HeartBeat (Stamp) VALUES (GETDATE())
GO 5

EXEC sp_rename 'dbo.StockLevels.OnHand', 'QuantityOnHand', 'COLUMN'
GO
  go
SELECT COUNT(*) FROM dbo.ReorderQueue
GO
