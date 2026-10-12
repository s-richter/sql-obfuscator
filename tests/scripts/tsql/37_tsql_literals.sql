-- Every kind of literal value. Used for the string, number and keep rules.
DECLARE @Name NVARCHAR(200) = N'Müller & Söhne GmbH';
DECLARE @Quote VARCHAR(50) = 'O''Brien''s "special" order';
DECLARE @Empty VARCHAR(10) = '';
DECLARE @Blank CHAR(1) = ' ';
DECLARE @Separator VARCHAR(5) = ' - ';
DECLARE @Comma CHAR(1) = ',';
DECLARE @NotAComment VARCHAR(40) = '-- this is text, not a comment';
DECLARE @AlsoText VARCHAR(40) = '/* still text */';
DECLARE @Flag CHAR(1) = 'Y';
DECLARE @Json NVARCHAR(MAX) = N'{"customer": {"name": "ACME", "vip": true}}';
DECLARE @Hex VARBINARY(8) = 0x1F8B0800;
DECLARE @Big BIGINT = 4711283;
DECLARE @Money MONEY = $1250.75;
DECLARE @Sci FLOAT = 1.5e6;

SELECT
    a.AccountId,
    a.Balance * 1.0 AS BalanceDecimal,
    a.Balance / 100.0 AS BalancePercent,
    a.Balance * 0.5 AS Half,
    -a.Balance AS Negated,
    CONVERT(VARCHAR(8), a.OpenedOn, 112) AS OpenedKey,
    CAST(a.Note AS VARCHAR(8000)) AS Note,
    CAST(a.Rate AS DECIMAL(18, 4)) AS Rate,
    JSON_VALUE(@Json, '$.customer.name') AS CustomerName,
    @Name + @Separator + a.Code AS Label
FROM dbo.Accounts AS a
WHERE a.AccountId = 4711283
   OR a.BranchCode = 42
   OR a.Limit IN (999, 1000, 1001)
   OR a.Balance > 1000.50
   OR a.Balance BETWEEN -250 AND 250000
   OR a.OpenedOn >= '2024-01-01'
   OR a.OpenedYear = 2024
   OR a.Code LIKE 'ACME%'
   OR a.Code LIKE '%[_]X' ESCAPE '\'
   OR a.Region IN (N'EMEA', N'APAC', 'N/A')
   OR a.Owner = @Quote
   OR a.Flag = @Flag
ORDER BY 1, 2 DESC;
