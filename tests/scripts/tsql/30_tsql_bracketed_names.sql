-- Names that need quoting: spaces, reserved words, punctuation, quotes inside names.
SELECT
    c.[Customer Name],
    c.[Order],
    c.[Select],
    c.[Net/Gross %],
    c.[Odd]]Bracket],
    c."Quoted Column",
    [c].[Customer Name] AS [Name Again],
    o.[2024 Total]
FROM [Sales DB].[dbo].[Customer Master] AS c
INNER JOIN [Sales DB].[dbo].[Order] AS o
    ON o.[Customer Id] = c.[Customer Id]
WHERE c.[Customer Name] <> ''
ORDER BY c.[Customer Name];
