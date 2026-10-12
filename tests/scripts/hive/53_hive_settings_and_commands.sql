-- Session settings and utility statements. Several of these switch sqlglot's tokenizer
-- into command mode.
SET hive.exec.dynamic.partition = true;
SET hive.exec.dynamic.partition.mode = nonstrict;
SET mapreduce.job.queuename = finance_etl;
SET hive.execution.engine=tez;

USE finance_mart;

MSCK REPAIR TABLE finance_mart.ledger_entries;
SHOW PARTITIONS finance_mart.ledger_entries;
SHOW TABLES IN finance_mart LIKE 'ledger*';
DESCRIBE FORMATTED finance_mart.ledger_entries;
ANALYZE TABLE finance_mart.ledger_entries PARTITION (posting_date = '2024-06-30') COMPUTE STATISTICS FOR COLUMNS account_no, amount;

ADD JAR hdfs:///libs/finance-udfs-2.4.1.jar;
CREATE TEMPORARY FUNCTION mask_iban AS 'com.corp.finance.udf.MaskIban';

SELECT mask_iban(l.iban), l.amount FROM ledger_entries l WHERE l.posting_date = '2024-06-30' LIMIT 100;

EXPLAIN SELECT count(*) FROM ledger_entries;
