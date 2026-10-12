SELECT k.Käufer, k.[Straße Nr], N'Ångström € 100' AS Märke -- övrigt 🚀
FROM dbo.Kunden AS k
WHERE k.Ort = N'Malmö';
