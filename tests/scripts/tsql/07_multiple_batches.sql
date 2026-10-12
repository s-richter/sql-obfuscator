-- Multiple batches with GO separators

-- Batch 1: Create a temporary table and populate it
CREATE TABLE #SalesData
(
  SalesId INT,
  SalesDate DATE,
  Amount DECIMAL(10, 2),
  Region VARCHAR(50)
);

INSERT INTO #SalesData
  (SalesId, SalesDate, Amount, Region)
SELECT
  OrderId,
  OrderDate,
  OrderTotal,
  Region
FROM Orders
WHERE OrderDate >= DATEADD(MONTH, -3, GETDATE());

GO

-- Batch 2: Query the temporary table
SELECT
  Region,
  COUNT(*) AS SalesCount,
  SUM(Amount) AS TotalAmount,
  AVG(Amount) AS AvgAmount
FROM #SalesData
GROUP BY Region
ORDER BY TotalAmount DESC;

GO

-- Batch 3: Update and cleanup
UPDATE #SalesData
SET Region = 'Other'
WHERE Region IS NULL;

SELECT *
FROM #SalesData
WHERE Region = 'Other';

DROP TABLE #SalesData;
