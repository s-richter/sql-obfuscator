FROM lake_raw.transactions t
INSERT OVERWRITE TABLE mart.tx_by_day PARTITION (tx_date)
    SELECT t.account_no, sum(t.amount) AS total, t.tx_date
    GROUP BY t.account_no, t.tx_date
INSERT INTO TABLE mart.tx_large PARTITION (tx_date = '2024-06-30')
    SELECT t.account_no, t.amount
    WHERE t.amount > 10000 AND t.tx_date = '2024-06-30';

INSERT OVERWRITE DIRECTORY '/exports/finance/tx_summary'
ROW FORMAT DELIMITED FIELDS TERMINATED BY ','
SELECT /*+ MAPJOIN(b) */ a.account_no, b.branch_name, a.total
FROM mart.tx_by_day a
JOIN ref.branches b ON b.branch_id = a.branch_id
WHERE a.tx_date = '2024-06-30'
DISTRIBUTE BY a.account_no
SORT BY a.account_no, a.total DESC;

SELECT s.account_no, s.total
FROM mart.tx_by_day TABLESAMPLE (BUCKET 3 OUT OF 16 ON account_no) s
CLUSTER BY s.account_no;

SELECT TRANSFORM (u.account_no, u.total)
       USING 'python3 score_accounts.py --model churn_v7'
       AS (account_no STRING, score DOUBLE)
FROM mart.tx_by_day u;

WITH ranked AS (
    SELECT account_no, total, dense_rank() OVER (ORDER BY total DESC) AS rnk
    FROM mart.tx_by_day
    WHERE tx_date = '2024-06-30'
)
SELECT account_no, total FROM ranked WHERE rnk <= 10
UNION ALL
SELECT 'OTHERS', sum(total) FROM ranked WHERE rnk > 10;
