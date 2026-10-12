-- Hive accepts both quote styles for strings and uses backslash escapes.
-- This comment mentions the real table hr.salaries.
SELECT
    s.employee_no,                      -- trailing comment about employee_no
    "double quoted string"   AS dq,
    'single quoted string'   AS sq,
    'it\'s escaped'          AS escaped_single,
    "say \"hello\""          AS escaped_double,
    'tab\there'              AS with_tab,
    '-- not a comment'       AS marker,
    ''                       AS empty_string,
    ','                      AS comma,
    1000                     AS four_digits,
    999                      AS three_digits,
    12.50                    AS with_decimals,
    1.5e3                    AS scientific,
    100L                     AS bigint_suffix,
    10Y                      AS tinyint_suffix,
    3.14BD                   AS decimal_suffix,
    DATE '2024-06-30'        AS typed_date,
    TIMESTAMP '2024-06-30 23:59:59' AS typed_ts,
    INTERVAL '7' DAY         AS one_week
FROM hr.salaries s
WHERE s.salary > 85000.00
  AND s.department IN ('R&D', "Sales", 'N/A')
  AND s.cost_center = 4711 -- sensitive number in a trailing comment position
  AND s.note NOT LIKE '%confidential%';
