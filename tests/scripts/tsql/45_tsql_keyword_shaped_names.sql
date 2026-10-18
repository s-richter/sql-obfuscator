-- Columns whose names are keywords or type names to the tokenizer, next to the real thing.
CREATE TABLE dbo.Notes (
    Id INT NOT NULL,
    Date DATE NOT NULL,
    Comment NVARCHAR(400) NULL,
    Format VARCHAR(20) NULL,
    Value DECIMAL(18, 2) NULL,
    Type VARCHAR(10) NULL
);

DECLARE @Cutoff DATE = CAST('2024-01-01' AS DATE);

SELECT
    n.Date,
    n.Comment,
    n.Format,
    n.Value,
    n.Type,
    [Date] AS BracketedDate,
    CAST(n.Date AS DATETIME) AS DateTimeValue,
    CONVERT(VARCHAR(10), n.Date, 120) AS Date,
    FORMAT(n.Value, 'N2') AS Formatted
FROM dbo.Notes n
WHERE n.Date >= @Cutoff
  AND Comment IS NOT NULL
ORDER BY Date, Format;

UPDATE dbo.Notes
SET Comment = 'reviewed', Format = 'plain'
WHERE Date < @Cutoff;
