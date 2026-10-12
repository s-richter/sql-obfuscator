SET NOCOUNT ON;
SET ANSI_NULLS ON;
SET TRANSACTION ISOLATION LEVEL READ UNCOMMITTED;

DECLARE @Batch TABLE (RowId INT IDENTITY(1, 1) PRIMARY KEY, ItemCode VARCHAR(30) NOT NULL, Qty INT);
DECLARE @RowCount INT, @Err INT, @Today DATE = CAST(GETDATE() AS DATE);

INSERT INTO @Batch (ItemCode, Qty)
SELECT i.ItemCode, i.Qty
FROM dbo.Inbound AS i WITH (NOLOCK, INDEX(IX_Inbound_Received))
WHERE i.ReceivedOn = @Today;

SELECT @RowCount = @@ROWCOUNT, @Err = @@ERROR;

IF OBJECT_ID('tempdb..#Totals') IS NOT NULL DROP TABLE #Totals;
CREATE TABLE #Totals (ItemCode VARCHAR(30), Total INT);
CREATE TABLE ##SharedTotals (ItemCode VARCHAR(30), Total INT);

INSERT INTO #Totals (ItemCode, Total)
SELECT b.ItemCode, SUM(b.Qty) FROM @Batch AS b GROUP BY b.ItemCode;

SELECT t.name AS TableName, c.name AS ColumnName, ty.name AS TypeName
FROM sys.tables AS t
JOIN sys.columns AS c ON c.object_id = t.object_id
JOIN sys.types AS ty ON ty.user_type_id = c.user_type_id
WHERE t.name = 'Inbound' AND SCHEMA_NAME(t.schema_id) = 'dbo';

SELECT SCOPE_IDENTITY() AS LastId, @@IDENTITY AS AnyId, @@SPID AS Spid, DB_NAME() AS Db, @@SERVERNAME AS Srv;

SELECT s.value AS Part
FROM STRING_SPLIT('a,b,c', ',') AS s;

EXEC sys.sp_executesql N'SELECT 1';
EXECUTE dbo.usp_Archive @ItemCount = @RowCount, @RunDate = @Today, @Verbose = 1;
DROP TABLE IF EXISTS #Totals;
