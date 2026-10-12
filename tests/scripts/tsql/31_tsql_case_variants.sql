-- The same names written in different casing. They are one name each.
SELECT
    Customers.CustomerId,
    CUSTOMERS.CUSTOMERID,
    customers.customerid,
    Customers.customerId,
    c.Region,
    C.REGION
FROM dbo.Customers
JOIN DBO.CUSTOMERS AS c
    ON c.CustomerID = customers.CUSTOMERID
WHERE Customers.Region = c.region;

select customerid, REGION from DBO.customers where Region is not null;
