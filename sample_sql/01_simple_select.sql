-- Simple SELECT statement with WHERE clause
SELECT UserId, UserName, EmailAddress, CreatedDate
FROM Users
WHERE Status = 'Active'
  AND CreatedDate >= '2025-01-01'
ORDER BY CreatedDate DESC;
