-- One table referenced with one, two, three and four name parts.
SELECT TOP 5 * FROM Invoices;
SELECT TOP 5 * FROM dbo.Invoices;
SELECT TOP 5 * FROM Billing.dbo.Invoices;
SELECT TOP 5 * FROM Billing..Invoices;
SELECT TOP 5 * FROM [LinkedSrv01].Billing.dbo.Invoices;

SELECT i.InvoiceId, Billing.dbo.Invoices.Amount, dbo.Invoices.Amount, Invoices.Amount
FROM Billing.dbo.Invoices AS i
JOIN Billing.finance.Ledgers AS l ON l.InvoiceId = i.InvoiceId
JOIN Archive.finance.Ledgers AS al ON al.LedgerId = l.LedgerId
WHERE Billing.dbo.fn_IsOpen(i.InvoiceId) = 1
  AND EXISTS (SELECT 1 FROM sys.objects AS so WHERE so.name = 'Invoices')
  AND EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS AS ic WHERE ic.TABLE_NAME = 'Invoices');
