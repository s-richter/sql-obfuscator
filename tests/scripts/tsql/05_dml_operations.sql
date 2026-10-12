-- INSERT, UPDATE, and DELETE statements
INSERT INTO Users (UserId, UserName, EmailAddress, Status, CreatedDate)
VALUES (1001, 'JohnDoe', 'john@example.com', 'Active', '2025-02-14');

UPDATE Users
SET LastLoginDate = GETDATE(),
    Status = 'Active'
WHERE UserId = 1001;

DELETE FROM Orders
WHERE OrderDate < '2020-01-01'
  AND Status = 'Cancelled';

INSERT INTO AuditLog (UserId, Action, ActionDate, OldValue, NewValue)
SELECT 
    UserId,
    'StatusChange',
    GETDATE(),
    'Inactive',
    'Active'
FROM Users
WHERE Status = 'Active'
  AND LastLoginDate > DATEADD(DAY, -30, GETDATE());
