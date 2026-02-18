# 📘 Project Specification

**SQL Identifier Obfuscator (Animal Mapper)**

Language: Python
Initial Interface: CLI
Primary Dialect: T-SQL (Microsoft SQL Server)
Parser: sqlglot (AST-based)

---

1️⃣ Project Overview
1.1 Purpose
The tool reads a T-SQL script and replaces:
• Table names
• Column names
• CTE names
• Temp table names
with randomly assigned animal names, while preserving:
• SQL syntax validity
• Identifier consistency
• Original SQL structure
The output must remain executable SQL, assuming the user creates matching schema objects.

---

1.2 Non-Goals
• ❌ No dynamic SQL handling (e.g., SQL inside string literals)
• ❌ No semantic resolution (no actual database inspection)
• ❌ No stored procedure parameter renaming (unless explicitly included later)
• ❌ No guarantee of semantic correctness — only syntactic validity

---

2️⃣ Functional Requirements
2.1 Input
• Accept a .sql file path as CLI argument:
python obfuscator.py script.sql
• Read entire file contents as string.
• Assume valid T-SQL input.

---

2.2 Output
• Print transformed SQL to stdout.
• Preserve formatting as much as parser allows.
• Ensure syntactic correctness.

---

2.3 Replacement Rules
2.3.1 Replace the Following:
Type Example
Tables Users
Columns UserId
CTE names RecentOrders
Temp tables #TempOrders
CREATE TABLE names Orders
INSERT target tables Orders
Column definitions UserId INT

---

2.3.2 Do NOT Replace
Type Example
SQL keywords SELECT, JOIN
String literals 'Users'
Numeric literals 100
Schema names dbo.Users (keep dbo)
Table aliases Users u (keep u)
Function names GETDATE()
Variables @UserId

---

2.4 Identifier Consistency Requirement
If:
SELECT UserId FROM Users WHERE UserId = 1
Then both UserId instances must map to the same animal.

---

2.5 Case & Bracket Handling
These must map to the same identifier:
UserId
[UserId]
USERID
Mapping must normalize internally.
Example:
SELECT [UserId] FROM Users WHERE UserId = 1
Output:
SELECT [wolf] FROM lion WHERE wolf = 1

---

3️⃣ Architecture Overview
CLI
↓
SQL Loader
↓
Parser (sqlglot)
↓
Identifier Registry
↓
AST Transformer
↓
SQL Generator
↓
Output

---

4️⃣ Detailed Component Specification

---

4.1 CLI Module
Responsibilities
• Parse CLI argument
• Validate file exists
• Read file contents
• Call obfuscation pipeline
• Print result
Tasks
• Use argparse
• Handle file-not-found
• Graceful parse error handling
Example:
python obfuscator.py input.sql

---

4.2 Animal Name Provider
4.2.1 Requirements
• Provide unique names
• Avoid collisions
• Deterministic option (optional)
4.2.2 Implementation Notes
Use:
animals = [
"cat", "dog", "mouse", "lion", "tiger",
"wolf", "bear", "eagle", "fox", "otter",
...
]
Maintain:
used = set()
Collision Handling
If animal pool exhausted:
• Append numeric suffix:
o cat1, cat2
• Or raise error (configurable)

---

4.3 Identifier Registry
4.3.1 Purpose
Central mapping:
original_identifier → obfuscated_identifier
4.3.2 Normalization Rules
• Lowercase key
• Strip brackets
• Preserve temp table prefix separately
Example
Input variants:
UserId
[UserId]
USERID
All normalize to:
userid
Mapping:
userid → wolf

---

4.3.3 Temp Table Handling
If identifier starts with #:
#TempOrders
Normalize:
temporders
Mapping:
temporders → lion
Output:
#lion

---

4.4 SQL Parsing
Use:
sqlglot.parse_one(sql, dialect="tsql")
Must support:
• CTE
• CREATE TABLE
• INSERT
• UPDATE
• DELETE
• JOIN
• WHERE
• Subqueries

---

4.5 AST Transformation
4.5.1 Strategy
Subclass sqlglot.Transformer.
Override only relevant node types.

---

4.5.2 Replace Table Nodes
Example Input:
SELECT _ FROM dbo.Users
AST:
Table(this='Users', db='dbo')
Replace:
• Only this
• Leave db untouched
Result:
SELECT _ FROM dbo.lion

---

4.5.3 Replace Column Nodes
Example:
SELECT u.UserId FROM Users u
Replace:
• UserId
• NOT u
Result:
SELECT u.wolf FROM lion u

---

4.5.4 Replace CTE Names
Input:
WITH RecentOrders AS (...)
SELECT \* FROM RecentOrders
Steps:
• Replace alias in WITH
• Replace table reference later
Mapping ensures consistency.

---

4.5.5 CREATE TABLE Handling
Input:
CREATE TABLE Orders (
UserId INT,
OrderDate DATETIME
)
Replace:
• Table name
• Column names
Output:
CREATE TABLE tiger (
wolf INT,
eagle DATETIME
)

---

4.5.6 INSERT Handling
Input:
INSERT INTO Orders (UserId, OrderDate)
Replace:
• Target table
• Column list

---

5️⃣ Edge Case Handling

---

5.1 Bracketed Identifiers
Input:
SELECT [UserId] FROM [Orders]
Replace value only.
Keep brackets intact.

---

5.2 Schema-Qualified Names
Input:
SELECT \* FROM dbo.Users
Only replace:
Users
Never:
dbo

---

5.3 Aliases
Input:
SELECT u.UserId
FROM Users u
Do NOT rename:
u
Unless explicitly desired (out of scope).

---

5.4 Column Name Collisions Across Tables
Example:
SELECT u.Id, o.Id
FROM Users u
JOIN Orders o ON ...
Both Id → same animal.
This is acceptable because:
• We are not preserving schema semantics.
• SQL remains valid.

---

6️⃣ Testing Specification
Create test cases for:

---

6.1 Simple SELECT
SELECT UserId FROM Users

---

6.2 JOIN
SELECT u.UserId
FROM Users u
JOIN Orders o ON u.UserId = o.UserId

---

6.3 CTE
WITH CTE AS (...)
SELECT \* FROM CTE

---

6.4 Temp Tables
CREATE TABLE #TempOrders (...)
SELECT \* FROM #TempOrders

---

6.5 CREATE TABLE + INSERT
CREATE TABLE Users (...)
INSERT INTO Users (...)

---

6.6 Mixed Brackets
SELECT [UserId] FROM Users WHERE UserId = 1

---

7️⃣ Performance Considerations
• Entire script parsed into AST
• Memory proportional to script size
• Acceptable for typical scripts (<1MB)
• Not designed for multi-GB SQL dumps

---

8️⃣ Error Handling
Parse Errors
If parser fails:
• Print helpful message
• Exit non-zero
Identifier Exhaustion
If animal list exhausted:
• Append numeric suffix
• Or configurable failure mode

---

9️⃣ Future Extensions
• Alias renaming
• Stored procedure name renaming
• Variable renaming
• Reversible mapping (store dictionary to JSON)
• Support for dynamic SQL (complex)

---

🔟 Estimated Task Breakdown
Task Est. Time
CLI scaffold 2 hours
Animal provider 1 hour
Registry implementation 3–4 hours
Basic AST transformer 1–2 days
CTE handling refinement 1 day
Temp table logic 0.5 day
Testing & debugging 2–3 days
Total: ~6–8 days.

---
