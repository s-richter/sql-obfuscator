-- Backtick-quoted names, reserved words as names, and mixed casing.
SELECT
    t.`order id`,
    t.`date`,
    t.`select`,
    T.Customer_Name,
    t.customer_name,
    `t`.`CUSTOMER_NAME`
FROM `Sales_Mart`.`Order Lines` t
JOIN sales_mart.Customers C ON c.customer_id = t.`customer id`
WHERE t.`date` >= '2024-01-01'
  AND C.Customer_Name RLIKE '^[A-Z]{3}-[0-9]+$';
