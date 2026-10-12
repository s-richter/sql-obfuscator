/* Header block comment.
   Mentions the real table dbo.Payroll and the column Salary. */
-- Line comment mentioning Salary
SELECT
    e.EmployeeId,      -- trailing comment after a column
    e.Salary /* inline block */ AS Pay,
    /* comment before a column */ e.Grade,
    '-- not a comment' AS Marker1,
    '/* not a comment */' AS Marker2
FROM dbo.Payroll AS e -- alias e
/* outer /* nested comment, which T-SQL allows */ still outer */
WHERE e.Salary > 0 --no space after dashes
  AND e.Grade <> '--' /* ends here */;
--
/**/
-- A comment with 'quotes' and "double quotes" and [brackets]
SELECT 1 AS One; -- last line has no newline after it