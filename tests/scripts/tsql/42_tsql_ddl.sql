CREATE SCHEMA hr AUTHORIZATION dbo;
GO

CREATE TABLE hr.Employees
(
    EmployeeId    INT IDENTITY(1000, 1) NOT NULL,
    NationalId    CHAR(11) NOT NULL,
    FullName      NVARCHAR(200) NOT NULL,
    Email         VARCHAR(320) NULL,
    Salary        DECIMAL(12, 2) NOT NULL CONSTRAINT DF_Employees_Salary DEFAULT (0),
    Bonus         AS (Salary * 0.1) PERSISTED,
    Grade         TINYINT NOT NULL CONSTRAINT CK_Employees_Grade CHECK (Grade BETWEEN 1 AND 12),
    DepartmentId  INT NOT NULL,
    HiredOn       DATE NOT NULL DEFAULT (GETDATE()),
    RowVer        ROWVERSION,
    CONSTRAINT PK_Employees PRIMARY KEY CLUSTERED (EmployeeId),
    CONSTRAINT UQ_Employees_NationalId UNIQUE (NationalId),
    CONSTRAINT FK_Employees_Departments FOREIGN KEY (DepartmentId)
        REFERENCES hr.Departments (DepartmentId) ON DELETE NO ACTION
);
GO

CREATE NONCLUSTERED INDEX IX_Employees_Department
    ON hr.Employees (DepartmentId, HiredOn DESC)
    INCLUDE (FullName, Salary)
    WHERE Grade >= 5;
GO

ALTER TABLE hr.Employees ADD TerminatedOn DATE NULL, Notes NVARCHAR(MAX) NULL;
ALTER TABLE hr.Employees DROP CONSTRAINT UQ_Employees_NationalId;
GO

CREATE OR ALTER VIEW hr.vw_ActiveEmployees
WITH SCHEMABINDING
AS
SELECT e.EmployeeId, e.FullName, e.DepartmentId, e.Salary + e.Bonus AS TotalPay
FROM hr.Employees AS e
WHERE e.TerminatedOn IS NULL;
GO

GRANT SELECT ON hr.vw_ActiveEmployees TO reporting_reader;
DENY SELECT ON hr.Employees (Salary, NationalId) TO reporting_reader;
TRUNCATE TABLE hr.EmployeeStaging;
DROP INDEX IX_Employees_Department ON hr.Employees;
